import asyncio
from datetime import datetime
from typing import Optional
import json
import re
import socket
import subprocess

import psutil
from ping3 import ping
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import Device, DeviceStatus, Metric
from app.db.session import AsyncSession as DbAsyncSession, engine
from app.core.config import settings
from app.services.realtime import broadcast_metric
from app.services.alerts import evaluate_metric_rules
from app.services.oui import ensure_oui_db, lookup_vendor

try:
    import redis.asyncio as aioredis
except Exception:
    aioredis = None

METRIC_INTERVAL_SECONDS = 30
_monitoring_task: Optional[asyncio.Task] = None
_last_net_stats: Optional[psutil._common.snetio] = None
_last_net_interface: Optional[str] = None
_last_net_time: Optional[datetime] = None
redis_client: Optional["aioredis.Redis"] = None


def _get_default_ipv4_address() -> Optional[str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return None


def _find_interface_for_ip(local_ip: str) -> Optional[str]:
    try:
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address == local_ip:
                    return name
    except Exception:
        pass
    return None


def _get_interface_counters(interface: Optional[str] = None) -> psutil._common.snetio:
    if interface:
        counters = psutil.net_io_counters(pernic=True)
        return counters.get(interface) or psutil.net_io_counters()
    return psutil.net_io_counters()


async def collect_latency_and_packet_loss() -> dict[str, float]:
    targets = ["8.8.8.8", "1.1.1.1"]
    latencies: list[float] = []
    lost = 0

    for target in targets:
        result = await asyncio.to_thread(ping, target, timeout=2)
        if result is None:
            lost += 1
        else:
            latencies.append(result * 1000)

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    packet_loss = (lost / len(targets)) * 100.0
    return {"latency": avg_latency, "packet_loss": packet_loss}


def collect_network_speed() -> dict[str, float]:
    global _last_net_stats, _last_net_time, _last_net_interface
    current_ip = _get_default_ipv4_address()
    current_interface = _find_interface_for_ip(current_ip) if current_ip else None
    current = _get_interface_counters(current_interface)
    now = datetime.utcnow()
    download_speed = 0.0
    upload_speed = 0.0

    if _last_net_stats is not None and _last_net_time is not None:
        elapsed = (now - _last_net_time).total_seconds()
        if elapsed > 0:
            download_bytes = current.bytes_recv - _last_net_stats.bytes_recv
            upload_bytes = current.bytes_sent - _last_net_stats.bytes_sent
            download_speed = (download_bytes * 8) / 1_000_000 / elapsed
            upload_speed = (upload_bytes * 8) / 1_000_000 / elapsed

    _last_net_stats = current
    _last_net_interface = current_interface
    _last_net_time = now
    return {"download_speed": round(download_speed, 2), "upload_speed": round(upload_speed, 2), "interface": current_interface or "unknown"}


async def _evaluate_alerts_background(metric: Metric) -> None:
    try:
        async with DbAsyncSession(engine) as session:
            await evaluate_metric_rules(session, metric)
    except Exception:
        pass


async def create_metric_record(session: AsyncSession) -> Metric:
    stats = await collect_latency_and_packet_loss()
    speeds = collect_network_speed()

    metric = Metric(
        timestamp=datetime.utcnow(),
        download_speed=speeds["download_speed"],
        upload_speed=speeds["upload_speed"],
        latency=stats["latency"],
        packet_loss=stats["packet_loss"],
    )
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    # push to redis (latest + recent list) if available
    # prepare metric payload
    metric_dict = {
        "id": metric.id,
        "timestamp": metric.timestamp.isoformat(),
        "download_speed": metric.download_speed,
        "upload_speed": metric.upload_speed,
        "latency": metric.latency,
        "packet_loss": metric.packet_loss,
        "interface": speeds.get("interface"),
    }

    # try to write to redis if available, but continue regardless
    try:
        global redis_client
        if redis_client is not None:
            await redis_client.set("metrics:latest", json.dumps(metric_dict))
            await redis_client.lpush("metrics:recent", json.dumps(metric_dict))
            await redis_client.ltrim("metrics:recent", 0, 119)
    except Exception:
        # ignore redis errors
        pass

    # broadcast to any connected websocket clients regardless of redis availability
    try:
        await broadcast_metric(metric_dict)
    except Exception:
        pass

    # evaluate alert rules asynchronously (don't block the metrics loop)
    try:
        asyncio.create_task(_evaluate_alerts_background(metric))
    except Exception:
        pass
    return metric


async def seed_devices(session: AsyncSession) -> None:
    """Discover devices via the OS ARP table and persist them.

    This uses `arp -a` on the host (Windows) or falls back to parsing
    `/proc/net/arp` on Unix. We add entries to the DB for any IPs not
    already present. Devices are marked `online` when discovered.
    """
    entries: list[tuple[str, str]] = []

    # Try platform-independent ARP collection. Prefer `arp -a` output
    try:
        output = await asyncio.to_thread(subprocess.check_output, ["arp", "-a"], text=True)
    except Exception:
        # Fallback for unix-like systems: try reading /proc/net/arp
        try:
            with open("/proc/net/arp", "r", encoding="utf-8") as f:
                raw = f.read()
            output = raw
        except Exception:
            output = ""

    if output:
        for line in output.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9A-Fa-f:-]{17}|[0-9A-Fa-f]{2}(-[0-9A-Fa-f]{2}){5})", line)
            if m:
                ip = m.group(1)
                mac = m.group(2).replace("-", ":").lower()
                entries.append((ip, mac))

    # Insert new discovered entries into DB and refresh existing rows with missing MAC/vendor
    for ip, mac in entries:
        try:
            existing = await session.exec(select(Device).where(Device.ip_address == ip))
            device = existing.first()
            vendor = None
            try:
                vendor = lookup_vendor(mac)
            except Exception:
                vendor = None

            if device is None:
                hostname = None
                try:
                    hostname = await asyncio.to_thread(socket.gethostbyaddr, ip)
                    hostname = hostname[0]
                except Exception:
                    hostname = None

                device = Device(
                    ip_address=ip,
                    mac_address=mac,
                    hostname=hostname,
                    vendor=vendor,
                    status=DeviceStatus.online,
                    last_seen=datetime.utcnow(),
                )
                session.add(device)
            else:
                updated = False
                if mac and device.mac_address != mac:
                    device.mac_address = mac
                    updated = True
                if device.vendor is None and vendor:
                    device.vendor = vendor
                    updated = True
                if device.last_seen is None:
                    device.last_seen = datetime.utcnow()
                    updated = True
                device.status = DeviceStatus.online
                if updated:
                    session.add(device)
        except Exception:
            # ignore per-entry failures
            pass

    try:
        await session.commit()
    except Exception:
        pass


async def enrich_existing_device_vendors(session: AsyncSession) -> None:
    """Fill vendor field for existing devices that have a MAC but no vendor yet."""
    try:
        results = await session.exec(select(Device).where(Device.mac_address != "", Device.vendor == None))
        to_update = results.all()
        updated = False
        for d in to_update:
            try:
                v = lookup_vendor(d.mac_address)
                if v:
                    d.vendor = v
                    session.add(d)
                    updated = True
            except Exception:
                continue
        if updated:
            try:
                await session.commit()
            except Exception:
                pass
    except Exception:
        pass


async def run_metric_scheduler() -> None:
    while True:
        try:
            async with DbAsyncSession(engine) as session:
                await create_metric_record(session)
        except Exception:
            pass
        await asyncio.sleep(METRIC_INTERVAL_SECONDS)


async def initialize_monitoring() -> None:
    global _monitoring_task
    # initialize redis client (best-effort)
    global redis_client
    if aioredis is not None:
        try:
            redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
            # test connection
            await redis_client.ping()
        except Exception:
            redis_client = None

    async with DbAsyncSession(engine) as session:
        # Ensure we have an OUI DB available (best-effort) and seed devices
        try:
            await ensure_oui_db()
        except Exception:
            pass
        await seed_devices(session)
        # Enrich any existing devices with vendor info
        try:
            await enrich_existing_device_vendors(session)
        except Exception:
            pass

    if _monitoring_task is None or _monitoring_task.done():
        _monitoring_task = asyncio.create_task(run_metric_scheduler())

    # Create the first metric in the background so startup is not blocked by network checks.
    try:
        asyncio.create_task(_create_initial_metric())
    except Exception:
        pass


async def _create_initial_metric() -> None:
    async with DbAsyncSession(engine) as session:
        try:
            await create_metric_record(session)
        except Exception:
            pass


async def shutdown_monitoring() -> None:
    global _monitoring_task
    if _monitoring_task is not None:
        _monitoring_task.cancel()
        try:
            await _monitoring_task
        except asyncio.CancelledError:
            pass
    # close redis client if open
    try:
        global redis_client
        if redis_client is not None:
            await redis_client.close()
            redis_client = None
    except Exception:
        pass

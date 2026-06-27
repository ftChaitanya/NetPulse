import asyncio
import ipaddress
import re
import socket
import subprocess
from datetime import datetime
from typing import List, Optional

from ping3 import ping
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import Device, DeviceStatus
from app.db.session import engine
from app.services.oui import lookup_vendor


def _resolve_vendor_sync(mac: str) -> str:
    """Best-effort vendor resolution. Look up local OUI first, then fall back to other sources."""
    if not mac:
        return ""
    try:
        vendor = lookup_vendor(mac)
        if vendor:
            return vendor
    except Exception:
        pass
    try:
        # try manuf package if available
        import manuf  # type: ignore

        m = manuf.MacParser()
        vendor = m.get_manuf(mac)
        return vendor or ""
    except Exception:
        pass

    try:
        resp = requests.get(f"https://api.macvendors.com/{mac}", timeout=3)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass

    return ""


def _parse_arp_table() -> dict[str, str]:
    """Return a mapping of IP -> MAC from the system arp table."""
    try:
        output = subprocess.check_output(["arp", "-a"], text=True, shell=False)
    except Exception:
        return {}

    entries: dict[str, str] = {}
    # Match IPv4 and MAC addresses in common formats
    for line in output.splitlines():
        ip_match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
        mac_match = re.search(r"([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})", line)
        if ip_match and mac_match:
            ip = ip_match.group(1)
            mac = mac_match.group(1).replace("-", ":").lower()
            entries[ip] = mac
    return entries


async def _async_ping(address: str, timeout: int = 1) -> Optional[float]:
    loop = asyncio.get_running_loop()
    try:
        # ping3.ping is blocking — run in threadpool
        return await loop.run_in_executor(None, ping, address, timeout)
    except Exception:
        return None


async def discover_network(cidr: Optional[str] = None, session=None) -> List[Device]:
    """Discover devices on the given CIDR (e.g. '192.168.1.0/24').

    If `cidr` is None, attempt to infer a /24 from the local IP, or fall back to common private ranges.
    Upserts discovered devices into the database using the provided `session`.
    Returns the list of Device objects that are currently online.
    """
    # Build host list
    networks = []
    if cidr:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except Exception:
            pass

    if not networks:
        # try infer local IP
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if local_ip and not local_ip.startswith("127."):
                base = local_ip.rsplit(".", 1)[0]
                networks.append(ipaddress.ip_network(f"{base}.0/24", strict=False))
        except Exception:
            pass

    if not networks:
        # fallback defaults
        for net in ("192.168.1.0/24", "192.168.0.0/24", "10.0.0.0/24"):
            networks.append(ipaddress.ip_network(net))

    hosts: List[str] = []
    for net in networks:
        for host in net.hosts():
            hosts.append(str(host))
        # only scan the first network
        break

    # run ping sweep concurrently with a limited pool
    sem = asyncio.Semaphore(200)

    async def ping_with_sem(addr: str) -> Optional[str]:
        async with sem:
            res = await _async_ping(addr, timeout=1)
            if res is not None:
                return addr
            return None

    tasks = [asyncio.create_task(ping_with_sem(h)) for h in hosts]
    results = await asyncio.gather(*tasks)
    alive = [r for r in results if r]

    # parse ARP table for MAC addresses
    arp_map = _parse_arp_table()

    # upsert into DB using the provided session
    upserted: List[Device] = []
    if session is None:
        async with AsyncSession(engine) as _session:
            for ip in alive:
                existing = await _session.exec(select(Device).where(Device.ip_address == ip))
                dev = existing.first()
                mac = arp_map.get(ip, "")
                vendor = ""
                if mac:
                    loop = asyncio.get_running_loop()
                    vendor = await loop.run_in_executor(None, _resolve_vendor_sync, mac)
                if dev is None:
                    dev = Device(
                        ip_address=ip,
                        mac_address=mac,
                        hostname="",
                        vendor=vendor,
                        status=DeviceStatus.online,
                        last_seen=datetime.utcnow(),
                    )
                    _session.add(dev)
                    await _session.commit()
                    await _session.refresh(dev)
                else:
                    dev.status = DeviceStatus.online
                    dev.last_seen = datetime.utcnow()
                    mac2 = arp_map.get(ip, dev.mac_address or "")
                    if mac2 and dev.mac_address != mac2:
                        dev.mac_address = mac2
                    if not dev.vendor and mac2:
                        loop = asyncio.get_running_loop()
                        vendor = await loop.run_in_executor(None, _resolve_vendor_sync, mac2)
                        if vendor:
                            dev.vendor = vendor
                    _session.add(dev)
                    await _session.commit()
                    await _session.refresh(dev)
                upserted.append(dev)
    else:
        for ip in alive:
            existing = await session.exec(select(Device).where(Device.ip_address == ip))
            dev = existing.first()
            mac = arp_map.get(ip, "")
            vendor = ""
            if mac:
                loop = asyncio.get_running_loop()
                vendor = await loop.run_in_executor(None, _resolve_vendor_sync, mac)
            if dev is None:
                dev = Device(
                    ip_address=ip,
                    mac_address=mac,
                    hostname="",
                    vendor=vendor,
                    status=DeviceStatus.online,
                    last_seen=datetime.utcnow(),
                )
                session.add(dev)
                await session.commit()
                await session.refresh(dev)
            else:
                dev.status = DeviceStatus.online
                dev.last_seen = datetime.utcnow()
                mac2 = arp_map.get(ip, dev.mac_address or "")
                if mac2 and dev.mac_address != mac2:
                    dev.mac_address = mac2
                if not dev.vendor and mac2:
                    loop = asyncio.get_running_loop()
                    vendor = await loop.run_in_executor(None, _resolve_vendor_sync, mac2)
                    if vendor:
                        dev.vendor = vendor
                session.add(dev)
                await session.commit()
                await session.refresh(dev)
            upserted.append(dev)

    return upserted


async def refresh_devices(session: AsyncSession) -> List[Device]:
    """Refresh existing device rows using the current ARP table.

    This updates saved devices with current MAC addresses and vendor info from the
    local ARP cache, without performing a full ping sweep.
    """
    arp_map = _parse_arp_table()
    if not arp_map:
        return []

    refreshed: List[Device] = []
    result = await session.exec(select(Device))
    for device in result.all():
        mac = arp_map.get(device.ip_address, device.mac_address or "")
        if not mac:
            continue

        vendor = device.vendor
        if not vendor:
            try:
                vendor = lookup_vendor(mac) or ""
            except Exception:
                vendor = ""

        updated = False
        if mac and device.mac_address != mac:
            device.mac_address = mac
            updated = True
        if vendor and device.vendor != vendor:
            device.vendor = vendor
            updated = True
        if updated:
            device.last_seen = datetime.utcnow()
            session.add(device)
            refreshed.append(device)

    if refreshed:
        await session.commit()
        for device in refreshed:
            await session.refresh(device)

    return refreshed

from fastapi import APIRouter, Depends
from sqlmodel import select
from app.db.models import Device
from app.db.session import get_session
from sqlmodel.ext.asyncio.session import AsyncSession

import socket
import datetime


router = APIRouter()


@router.get("/", response_model=list[Device])
async def list_devices(
    all: str | None = None,
    include_all: str | None = None,
    minutes: int | None = 10,
    session: AsyncSession = Depends(get_session),
):
    """List devices.

    By default this returns recent devices on the server's active /24 subnet
    (last `minutes`, default 10). Set `all=true` to return all historical devices.
    """
    # support both `all` and `include_all` query params (string or bool)
    raw_all = all if all is not None else include_all
    all_flag = False
    try:
        if isinstance(raw_all, str):
            all_flag = raw_all.lower() in ("1", "true", "t", "yes")
        else:
            all_flag = bool(raw_all)
    except Exception:
        all_flag = False

    if all_flag:
        result = await session.exec(select(Device).order_by(Device.last_seen.desc()))
        return result.all()

    # determine local IPv4 and use /24 prefix as a sensible default
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = None
    finally:
        try:
            s.close()
        except Exception:
            pass

    if local_ip:
        prefix = ".".join(local_ip.split(".")[:3]) + "."
    else:
        prefix = None

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes or 10)

    # fetch candidates (limit by prefix when possible) then apply
    # a Python-side time filter to avoid DB datetime format issues
    if prefix:
        stmt = select(Device).where(Device.ip_address.like(f"{prefix}%")).order_by(Device.last_seen.desc())
    else:
        stmt = select(Device).order_by(Device.last_seen.desc())

    result = await session.exec(stmt)
    candidates = result.all()

    def parse_last_seen(val):
        if val is None:
            return None
        if isinstance(val, datetime.datetime):
            return val
        s = str(val)
        try:
            # try ISO first
            return datetime.datetime.fromisoformat(s)
        except Exception:
            # fallback common format
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.datetime.strptime(s, fmt)
                except Exception:
                    continue
        return None

    filtered = []
    for d in candidates:
        ls = parse_last_seen(getattr(d, "last_seen", None))
        if ls is None:
            continue
        # assume stored times are UTC / naive — compare with cutoff (UTC)
        if ls >= cutoff:
            filtered.append(d)
    return filtered


@router.post("/discover", response_model=list[Device])
async def discover_devices(cidr: str | None = None, session: AsyncSession = Depends(get_session)):
    """Trigger a network discovery scan. Optional `cidr` to specify subnet (e.g. 192.168.1.0/24)."""
    from app.services.discovery import discover_network

    devices = await discover_network(cidr=cidr, session=session)
    return devices


@router.post("/refresh", response_model=list[Device])
async def refresh_devices(session: AsyncSession = Depends(get_session)):
    """Refresh existing devices from the local ARP table and update MAC/vendor info."""
    from app.services.discovery import refresh_devices as refresh_devices_service

    devices = await refresh_devices_service(session=session)
    return devices

from fastapi import APIRouter, Depends
from sqlmodel import select
from app.db.models import Device, Metric, Alert
from app.db.session import get_session
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()

@router.get("/")
async def overview(session: AsyncSession = Depends(get_session)):
    devices = await session.exec(select(Device))
    latest_metric = await session.exec(select(Metric).order_by(Metric.timestamp.desc()).limit(1))
    alerts = await session.exec(select(Alert).where(Alert.resolved == False))
    return {
        "device_count": len(devices.all()),
        "latest_metric": latest_metric.first(),
        "active_alerts": len(alerts.all()),
    }

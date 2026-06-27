from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlmodel import select
from app.db.models import Metric
from app.db.session import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi.responses import StreamingResponse, JSONResponse

router = APIRouter()

@router.get("/latest", response_model=Metric)
async def latest_metric(session: AsyncSession = Depends(get_session)):
    result = await session.exec(
        select(Metric).order_by(Metric.timestamp.desc()).limit(1)
    )
    metric = result.first()
    return metric or Metric()

@router.get("/history", response_model=list[Metric])
async def metric_history(session: AsyncSession = Depends(get_session), limit: int = 50):
    result = await session.exec(
        select(Metric).order_by(Metric.timestamp.desc()).limit(limit)
    )
    return result.all()


def _generate_bytes(total_bytes: int, chunk_size: int = 65536):
    chunk = b"0" * chunk_size
    sent = 0
    while sent < total_bytes:
        remaining = total_bytes - sent
        to_send = chunk if remaining >= chunk_size else b"0" * remaining
        yield to_send
        sent += len(to_send)


@router.get("/speedtest/download")
async def metrics_speed_download(mb: int = 10):
    total_bytes = int(mb) * 1024 * 1024
    return StreamingResponse(_generate_bytes(total_bytes), headers={"Content-Type": "application/octet-stream"})


@router.post("/speedtest/upload")
async def metrics_speed_upload(request: Request):
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk or b"")
    except Exception:
        return JSONResponse({"error": "failed to read upload stream"}, status_code=500)
    return {"bytes": total}

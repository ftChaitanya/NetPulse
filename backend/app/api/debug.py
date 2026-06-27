from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.models import Alert, AlertSeverity
from app.db.session import get_session
from app.services.realtime import broadcast_event
import asyncio
from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse

router = APIRouter()

def _generate_bytes(total_bytes: int, chunk_size: int = 65536):
    chunk = b"0" * chunk_size
    sent = 0
    while sent < total_bytes:
        remaining = total_bytes - sent
        to_send = chunk if remaining >= chunk_size else b"0" * remaining
        yield to_send
        sent += len(to_send)


@router.get("/speedtest/download")
async def debug_speed_download(mb: int = 10):
    total_bytes = int(mb) * 1024 * 1024
    return StreamingResponse(_generate_bytes(total_bytes), headers={"Content-Type": "application/octet-stream"})


@router.post("/speedtest/upload")
async def debug_speed_upload(request: Request):
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk or b"")
            if total % (1024 * 1024) == 0:
                await asyncio.sleep(0)
    except Exception:
        return JSONResponse({"error": "failed to read upload stream"}, status_code=500)
    return {"bytes": total}

@router.get("/trigger_alert")
async def trigger_alert(session: AsyncSession = Depends(get_session)):
    """Dev endpoint: create and broadcast a test alert."""
    alert = Alert(severity=AlertSeverity.critical, message="Dev triggered alert - check UI")
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    # broadcast to connected websocket clients
    try:
        await broadcast_event({
            "type": "alert",
            "payload": {
                "id": alert.id,
                "severity": alert.severity,
                "message": alert.message,
                "created_at": alert.created_at.isoformat(),
            },
        })
    except Exception:
        pass
    return {"ok": True, "alert_id": alert.id}

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

from app.services import realtime as realtime_service

router = APIRouter()


@router.websocket("/metrics")
async def websocket_metrics(ws: WebSocket):
    await ws.accept()
    await realtime_service.register(ws)
    try:
        # Keep connection open; clients don't need to send anything.
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_service.unregister(ws)

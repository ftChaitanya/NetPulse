from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio

router = APIRouter()


def _generate_bytes(total_bytes: int, chunk_size: int = 65536):
    chunk = b"0" * chunk_size
    sent = 0
    while sent < total_bytes:
        remaining = total_bytes - sent
        to_send = chunk if remaining >= chunk_size else b"0" * remaining
        yield to_send
        sent += len(to_send)


@router.get("/download")
async def download(mb: int = 10):
    """Stream `mb` megabytes of data to the client for active download testing."""
    total_bytes = int(mb) * 1024 * 1024
    headers = {"Content-Type": "application/octet-stream"}
    return StreamingResponse(_generate_bytes(total_bytes), headers=headers)


@router.post("/upload")
async def upload(request: Request):
    """Accept an upload stream and return the total bytes received.

    Client should stream a blob and measure time client-side — server returns byte count.
    """
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk or b"")
            # yield to event loop occasionally
            if total % (1024 * 1024) == 0:
                await asyncio.sleep(0)
    except Exception:
        return JSONResponse({"error": "failed to read upload stream"}, status_code=500)

    return {"bytes": total}

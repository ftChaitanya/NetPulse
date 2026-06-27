from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api import devices, metrics, alerts, overview, debug
from app.api import realtime
from app.api import speedtest
from app.api import iperf
from app.core.config import settings
from app.services.monitoring import shutdown_monitoring

app = FastAPI(title="NetPulse Campus Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(overview.router, prefix="/api/overview", tags=["overview"])
app.include_router(realtime.router, prefix="/ws", tags=["realtime"])
app.include_router(debug.router, prefix="/api/debug", tags=["debug"])
app.include_router(speedtest.router, prefix="/api/speedtest", tags=["speedtest"])
app.include_router(iperf.router, prefix="/api/iperf", tags=["iperf"])

@app.on_event("startup")
async def on_startup():
    from app.core.startup import startup_event

    await startup_event()

@app.on_event("shutdown")
async def on_shutdown():
    await shutdown_monitoring()

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "netpulse-backend"}


@app.get("/")
async def root() -> RedirectResponse:
    """Redirect root to the interactive docs."""
    return RedirectResponse(url="/docs")

from app.db.session import init_db
from app.services.monitoring import initialize_monitoring


async def startup_event() -> None:
    await init_db()
    await initialize_monitoring()

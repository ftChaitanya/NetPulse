import asyncio
from datetime import datetime
from app.db.session import AsyncSession, engine
from app.db.models import Metric
from app.services.alerts import evaluate_metric_rules

async def main():
    async with AsyncSession(engine) as session:
        metric = Metric(
            timestamp=datetime.utcnow(),
            download_speed=0.5,
            upload_speed=0.1,
            latency=250.0,
            packet_loss=7.0,
        )
        session.add(metric)
        await session.commit()
        await session.refresh(metric)
        alert = await evaluate_metric_rules(session, metric)
        print(f"METRIC_ID={metric.id} ALERT_ID={alert.id if alert else 'NO_ALERT'}")

asyncio.run(main())

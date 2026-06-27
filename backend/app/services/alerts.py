from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import Alert, AlertSeverity, Metric
from app.services.realtime import broadcast_event


async def evaluate_metric_rules(session: AsyncSession, metric: Metric) -> Optional[Alert]:
    from app.services.monitoring import redis_client
    messages = []
    severity = AlertSeverity.info

    if metric.packet_loss is not None and metric.packet_loss > 5:
        severity = AlertSeverity.critical
        messages.append(f"High packet loss: {metric.packet_loss}%")

    if metric.latency is not None:
        if metric.latency > 200:
            severity = AlertSeverity.critical
            messages.append(f"Very high latency: {metric.latency:.0f} ms")
        elif metric.latency > 100:
            if severity != AlertSeverity.critical:
                severity = AlertSeverity.warning
            messages.append(f"High latency: {metric.latency:.0f} ms")

    if metric.download_speed is not None and metric.download_speed < 5:
        if severity == AlertSeverity.info:
            severity = AlertSeverity.warning
        messages.append(f"Low download speed: {metric.download_speed} Mbps")

    if not messages:
        return None

    alert = Alert(severity=severity, message="; ".join(messages))
    session.add(alert)
    await session.commit()
    await session.refresh(alert)

    # store active alert in redis set and broadcast
    try:
        if redis_client is not None:
            await redis_client.sadd("alerts:active", alert.id)
            await redis_client.set(f"alert:{alert.id}", alert.message)
    except Exception:
        pass

    try:
        await broadcast_event({"type": "alert", "payload": {"id": alert.id, "severity": alert.severity, "message": alert.message, "created_at": alert.created_at.isoformat()}})
    except Exception:
        pass

    return alert

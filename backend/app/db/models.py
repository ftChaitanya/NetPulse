from datetime import datetime
from enum import Enum
from sqlmodel import SQLModel, Field


class DeviceStatus(str, Enum):
    online = "online"
    offline = "offline"


class Device(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ip_address: str
    mac_address: str
    hostname: str | None = None
    vendor: str | None = None
    status: DeviceStatus = DeviceStatus.offline
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class Metric(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    download_speed: float | None = None
    upload_speed: float | None = None
    latency: float | None = None
    packet_loss: float | None = None


class AlertSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class Alert(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    severity: AlertSeverity
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = Field(default=False, index=True)


class UptimeCheck(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    website: str
    status: str
    response_time: float | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)

from datetime import datetime

from pydantic import BaseModel, Field


class AutomationSettingsRead(BaseModel):
    enabled: bool = True
    low_stock_threshold: int = Field(default=10, ge=0, le=10000)
    expiry_notice_days: int = Field(default=30, ge=1, le=365)


class AutomationSettingsUpdate(AutomationSettingsRead):
    pass


class AutomationAlertRead(BaseModel):
    id: int
    kind: str
    title: str
    message: str
    first_seen_at: datetime
    last_seen_at: datetime


class AutomationRunRead(BaseModel):
    as_of_date: str
    active_alerts: int
    new_alerts: int

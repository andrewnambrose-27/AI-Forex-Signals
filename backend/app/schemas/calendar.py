from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


CalendarHealth = Literal["healthy", "stale", "unavailable"]


class EconomicEventRead(BaseModel):
    internal_id: str
    provider: str
    provider_event_id: str | None = None
    title: str
    country: str | None = None
    currency: str
    event_time_utc: datetime
    impact: Literal["low", "medium", "high", "unknown"]
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    revised_previous: str | None = None
    unit: str | None = None
    source: str | None = None
    status: Literal["scheduled", "released", "revised", "cancelled"]
    raw_payload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CalendarSettingsRead(BaseModel):
    provider: str = "fmp"
    sync_interval_minutes: int = 15
    block_before_high_minutes: int = 60
    block_after_high_minutes: int = 30
    block_before_medium_minutes: int = 20
    block_after_medium_minutes: int = 10


class CalendarSettingsUpdate(BaseModel):
    provider: str | None = Field(None, examples=["fmp", "fxstreet", "trading_economics"])
    sync_interval_minutes: int | None = Field(None, ge=1, le=1440)
    block_before_high_minutes: int | None = Field(None, ge=0, le=1440)
    block_after_high_minutes: int | None = Field(None, ge=0, le=1440)
    block_before_medium_minutes: int | None = Field(None, ge=0, le=1440)
    block_after_medium_minutes: int | None = Field(None, ge=0, le=1440)


class CalendarEventsRead(BaseModel):
    calendar_status: CalendarHealth
    events: list[EconomicEventRead]


class PairRiskRead(BaseModel):
    pair: str
    currencies: list[str]
    blocked: bool
    reason: str | None = None
    block_before_minutes: int
    block_after_minutes: int
    event: EconomicEventRead | None = None
    upcoming_events: list[EconomicEventRead] = []
    calendar_status: CalendarHealth
    last_synced_at: datetime | None = None


class CalendarSyncRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None


class CalendarSyncRead(BaseModel):
    provider: str
    synced_events: int
    start_date: date
    end_date: date
    calendar_status: CalendarHealth
    last_successful_sync_at: datetime | None


class CalendarStatusRead(BaseModel):
    provider: str
    calendar_status: CalendarHealth
    configured: bool
    last_sync_attempt_at: datetime | None
    last_successful_sync_at: datetime | None
    next_sync_due_at: datetime | None
    last_error: str | None
    stored_event_count: int
    upcoming_event_count: int
    sync_interval_minutes: int

from datetime import datetime

from pydantic import BaseModel, Field


class EconomicEventRead(BaseModel):
    id: int | None = None
    provider: str
    external_id: str | None = None
    country: str | None = None
    currency: str
    title: str
    impact: str
    event_time: datetime
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class CalendarSettingsRead(BaseModel):
    provider: str = "mock"
    block_before_high_impact_minutes: int = 60
    block_after_high_impact_minutes: int = 30


class CalendarSettingsUpdate(BaseModel):
    provider: str | None = Field(None, examples=["mock", "finnhub", "fxstreet"])
    block_before_high_impact_minutes: int | None = Field(None, ge=0, le=1440)
    block_after_high_impact_minutes: int | None = Field(None, ge=0, le=1440)


class PairRiskRead(BaseModel):
    pair: str
    currencies: list[str]
    blocked: bool
    reason: str | None = None
    block_before_minutes: int
    block_after_minutes: int
    event: EconomicEventRead | None = None
    upcoming_events: list[EconomicEventRead] = []

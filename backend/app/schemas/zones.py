from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PriceZoneRead(BaseModel):
    lower_price: float
    upper_price: float
    centre_price: float
    type: Literal["support", "resistance", "mixed"]
    confirmed_touches: int
    first_touch_time: datetime
    most_recent_touch_time: datetime
    strength_score: int
    broken: bool
    retested: bool
    higher_timeframe_confluence: bool
    break_direction: Literal["above", "below"] | None = None
    broken_at: datetime | None = None
    retested_at: datetime | None = None
    rejection_strength: float


class ZoneAnalysisRead(BaseModel):
    symbol: str
    timeframe: str
    higher_timeframe: str | None
    atr_14: float | None
    clustering_distance_atr: float
    break_buffer_atr: float
    closed_candle_count: int
    zones: list[PriceZoneRead]
    reasons: list[str]

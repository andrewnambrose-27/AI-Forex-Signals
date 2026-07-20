from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TrendLineRead(BaseModel):
    start_time: datetime
    start_price: float
    end_time: datetime
    end_price: float
    direction: Literal["bullish", "bearish"]
    role: Literal["primary", "secondary"]
    touch_count: int
    confidence_score: int
    status: Literal["active", "broken"]
    broken_at: datetime | None
    bounce_detected: bool
    bounce_at: datetime | None
    break_retested: bool
    retested_at: datetime | None
    failed_retest: bool
    horizontal_zone_confluence: bool
    first_anchor_confirmed_at: datetime
    last_anchor_confirmed_at: datetime


class TrendLineAnalysisRead(BaseModel):
    symbol: str
    timeframe: str
    atr_14: float | None
    touch_tolerance_atr: float
    break_buffer_atr: float
    minimum_anchor_distance: int
    closed_candle_count: int
    lines: list[TrendLineRead]
    reasons: list[str]

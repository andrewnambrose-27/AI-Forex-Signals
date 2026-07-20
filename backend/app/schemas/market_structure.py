from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SwingPointRead(BaseModel):
    index: int
    time: datetime
    confirmed_at: datetime
    price: float
    kind: Literal["high", "low"]


class StructurePointRead(SwingPointRead):
    classification: Literal["HH", "HL", "LH", "LL"]


class MarketStructureRead(BaseModel):
    symbol: str
    timeframe: str
    latest_confirmed_swing_high: SwingPointRead | None
    latest_confirmed_swing_low: SwingPointRead | None
    recent_structure_points: list[StructurePointRead]
    direction: Literal["bullish", "bearish", "ranging", "insufficient_data"]
    confidence_score: int
    reasons: list[str]
    left_candles: int
    right_candles: int
    closed_candle_count: int

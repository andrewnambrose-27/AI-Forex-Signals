from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TimeframeStateRead(BaseModel):
    timeframe: str
    role: Literal["entry", "confirmation", "directional_bias"]
    direction: Literal["bullish", "bearish", "neutral", "insufficient_data"]
    ema_alignment: Literal["bullish", "bearish", "neutral", "insufficient_data"]
    market_structure: str
    adx: float | None
    trend_strength: Literal["strong", "moderate", "weak", "insufficient_data"]
    support_zones: int
    resistance_zones: int
    zone_context: Literal["support_nearby", "resistance_nearby", "balanced", "none"]
    recent_structure_break: Literal["bullish", "bearish", "none"]
    confidence_score: int
    closed_candle_count: int
    latest_closed_at: datetime | None
    reasons: list[str]


class MultiTimeframeAnalysisRead(BaseModel):
    entry_timeframe: str
    confirmation_timeframe: str | None
    directional_bias_timeframe: str | None
    entry_state: TimeframeStateRead
    confirmation_state: TimeframeStateRead | None
    higher_timeframe_state: TimeframeStateRead | None
    result: Literal["aligned", "mixed", "conflicting"]
    overall_direction: Literal["bullish", "bearish", "neutral", "insufficient_data"]
    overall_summary: str
    score_penalty: int
    strong_conflict: bool
    reasons: list[str]


class MultiTimeframeResponse(MultiTimeframeAnalysisRead):
    symbol: str

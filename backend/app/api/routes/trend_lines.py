from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession
from app.api.routes.ig import fetch_candles
from app.api.routes.market_structure import _resolve_epic
from app.schemas.trend_lines import TrendLineAnalysisRead
from app.services.support_resistance import detect_support_resistance_zones
from app.services.trend_lines import detect_trend_lines


router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/trend-lines", response_model=TrendLineAnalysisRead)
def get_trend_lines(
    db: DbSession,
    symbol: str = Query(..., min_length=6, max_length=12),
    timeframe: str = Query("5m"),
    left_candles: int = Query(3, ge=1, le=20),
    right_candles: int = Query(3, ge=1, le=20),
    minimum_anchor_distance: int = Query(5, ge=1, le=100),
    touch_tolerance_atr: float = Query(0.25, gt=0, le=2),
    break_buffer_atr: float = Query(0.1, ge=0, le=2),
    violation_buffer_atr: float = Query(0.5, ge=0, le=3),
) -> dict[str, Any]:
    normalized_symbol = symbol.upper().replace("/", "")
    normalized_timeframe = timeframe.lower()
    if normalized_timeframe not in {"5m", "15m", "1h", "4h", "1d"}:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe}")

    epic = _resolve_epic(normalized_symbol)
    candles = fetch_candles(db=db, epic=epic, resolution=normalized_timeframe, limit=1000)["candles"]
    zones = detect_support_resistance_zones(
        candles,
        left_candles=left_candles,
        right_candles=right_candles,
        max_zones=8,
    ).zones
    result = detect_trend_lines(
        candles,
        left_candles=left_candles,
        right_candles=right_candles,
        minimum_anchor_distance=minimum_anchor_distance,
        touch_tolerance_atr=touch_tolerance_atr,
        break_buffer_atr=break_buffer_atr,
        violation_buffer_atr=violation_buffer_atr,
        horizontal_zones=zones,
    )
    return {"symbol": normalized_symbol, "timeframe": normalized_timeframe, **asdict(result)}

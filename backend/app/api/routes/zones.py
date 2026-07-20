from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession
from app.api.routes.ig import fetch_candles
from app.api.routes.market_structure import _resolve_epic
from app.schemas.zones import ZoneAnalysisRead
from app.services.support_resistance import detect_support_resistance_zones


router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/zones", response_model=ZoneAnalysisRead)
def get_zones(
    db: DbSession,
    symbol: str = Query(..., min_length=6, max_length=12),
    timeframe: str = Query("5m"),
    left_candles: int = Query(3, ge=1, le=20),
    right_candles: int = Query(3, ge=1, le=20),
    clustering_distance_atr: float = Query(0.25, gt=0, le=2),
    break_buffer_atr: float = Query(0.1, ge=0, le=2),
    max_zones: int = Query(8, ge=5, le=8),
) -> dict[str, Any]:
    normalized_symbol = symbol.upper().replace("/", "")
    normalized_timeframe = timeframe.lower()
    if normalized_timeframe not in {"5m", "15m", "1h", "4h", "1d"}:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe}")

    epic = _resolve_epic(normalized_symbol)
    primary = fetch_candles(db=db, epic=epic, resolution=normalized_timeframe, limit=1000)["candles"]
    higher_timeframe = _higher_timeframe(normalized_timeframe)
    higher_zones = []
    if higher_timeframe is not None:
        higher = fetch_candles(db=db, epic=epic, resolution=higher_timeframe, limit=1000)["candles"]
        higher_zones = detect_support_resistance_zones(
            higher,
            left_candles=left_candles,
            right_candles=right_candles,
            clustering_distance_atr=clustering_distance_atr,
            break_buffer_atr=break_buffer_atr,
        ).zones

    result = detect_support_resistance_zones(
        primary,
        left_candles=left_candles,
        right_candles=right_candles,
        clustering_distance_atr=clustering_distance_atr,
        break_buffer_atr=break_buffer_atr,
        higher_timeframe_zones=higher_zones,
        max_zones=max_zones,
    )
    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "higher_timeframe": higher_timeframe,
        **asdict(result),
    }


def _higher_timeframe(timeframe: str) -> str | None:
    return {"5m": "15m", "15m": "1h", "1h": "4h", "4h": "1d", "1d": None}[timeframe]

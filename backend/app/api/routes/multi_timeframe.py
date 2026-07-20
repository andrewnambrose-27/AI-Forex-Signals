from dataclasses import asdict
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.routes.ig import fetch_candles
from app.api.routes.market_structure import _resolve_epic
from app.schemas.multi_timeframe import MultiTimeframeResponse
from app.services.multi_timeframe import analyze_multi_timeframe, required_timeframes


router = APIRouter(prefix="/analysis", tags=["analysis"])
ANALYSIS_CACHE_SECONDS = 60
_analysis_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_analysis_cache_lock = Lock()


@router.get("/multi-timeframe", response_model=MultiTimeframeResponse)
def get_multi_timeframe_analysis(
    db: DbSession,
    symbol: str = Query(..., min_length=6, max_length=12),
    timeframe: str = Query("5m", pattern="^(5m|15m|1h|4h|1d)$"),
) -> dict[str, Any]:
    normalized_symbol = symbol.upper().replace("/", "")
    normalized_timeframe = timeframe.lower()
    cache_key = (normalized_symbol, normalized_timeframe)
    with _analysis_cache_lock:
        cached = _analysis_cache.get(cache_key)
        if cached and monotonic() - cached[0] < ANALYSIS_CACHE_SECONDS:
            return cached[1]
    epic = _resolve_epic(normalized_symbol)
    candles_by_timeframe = {
        item: fetch_candles(db=db, epic=epic, resolution=item, limit=_limit(item))["candles"]
        for item in required_timeframes(normalized_timeframe)
    }
    result = analyze_multi_timeframe(candles_by_timeframe, entry_timeframe=normalized_timeframe)
    response = {"symbol": normalized_symbol, **asdict(result)}
    with _analysis_cache_lock:
        _analysis_cache[cache_key] = (monotonic(), response)
    return response


def _limit(timeframe: str) -> int:
    return {"5m": 1000, "15m": 1000, "1h": 750, "4h": 500, "1d": 400}[timeframe]

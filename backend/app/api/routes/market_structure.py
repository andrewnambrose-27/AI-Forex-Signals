from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession
from app.api.routes.ig import fetch_candles, get_ig_client
from app.schemas.market_structure import MarketStructureRead
from app.services.ig_client import IGClientError
from app.services.market_structure import analyze_market_structure


router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/market-structure", response_model=MarketStructureRead)
def get_market_structure(
    db: DbSession,
    symbol: str = Query(..., min_length=6, max_length=12),
    timeframe: str = Query("5m"),
    left_candles: int = Query(3, ge=1, le=20),
    right_candles: int = Query(3, ge=1, le=20),
    recent_limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    normalized_symbol = symbol.upper().replace("/", "")
    if timeframe.lower() not in {"5m", "15m", "1h", "4h", "1d"}:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe}")

    epic = _resolve_epic(normalized_symbol)
    candle_payload = fetch_candles(db=db, epic=epic, resolution=timeframe, limit=1000)
    result = analyze_market_structure(
        candle_payload["candles"],
        left_candles=left_candles,
        right_candles=right_candles,
        recent_limit=recent_limit,
    )
    return {"symbol": normalized_symbol, "timeframe": timeframe.lower(), **asdict(result)}


def _resolve_epic(symbol: str) -> str:
    client = get_ig_client()
    slash_symbol = f"{symbol[:3]}/{symbol[3:6]}"
    try:
        for query in (slash_symbol, symbol):
            markets = client.search_markets(query).get("markets", [])
            for market in markets:
                searchable = " ".join(str(market.get(key, "")) for key in ("instrumentName", "marketName", "epic")).upper()
                if slash_symbol in searchable or symbol in searchable.replace("/", ""):
                    return str(market["epic"])
            if markets and markets[0].get("epic"):
                return str(markets[0]["epic"])
    except IGClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=f"No IG market found for {symbol}")

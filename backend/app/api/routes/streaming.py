from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ig_client import IGClient, IGClientError
from app.services.ig_streaming import IGStreamingClient

router = APIRouter(tags=["streaming"])


@dataclass
class LiveCandle:
    start_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def update(self, price: Decimal) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price

    def payload(self, *, is_closed: bool) -> dict[str, Any]:
        return {
            "time": self.start_time,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "isClosed": is_closed,
        }


@router.websocket("/ws/prices")
async def stream_prices(websocket: WebSocket) -> None:
    await websocket.accept()
    symbol = (websocket.query_params.get("symbol") or "").upper()
    timeframe = (websocket.query_params.get("timeframe") or "1h").lower()

    try:
        duration_seconds = _timeframe_seconds(timeframe)
        epic = websocket.query_params.get("epic") or _resolve_epic(symbol)
        await websocket.send_json({"type": "stream_status", "status": "connected", "symbol": symbol, "timeframe": timeframe})

        current: LiveCandle | None = None
        async for tick in IGStreamingClient().stream_market_prices(epic):
            start_time = _candle_start_time(tick.update_time, duration_seconds)
            if current is None:
                current = LiveCandle(start_time=start_time, open=tick.mid, high=tick.mid, low=tick.mid, close=tick.mid)
            elif start_time > current.start_time:
                await websocket.send_json(
                    {
                        "type": "candle_update",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "candle": current.payload(is_closed=True),
                    }
                )
                current = LiveCandle(start_time=start_time, open=tick.mid, high=tick.mid, low=tick.mid, close=tick.mid)
            else:
                current.update(tick.mid)

            await websocket.send_json(
                {
                    "type": "candle_update",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "candle": current.payload(is_closed=False),
                    "bid": float(tick.bid),
                    "offer": float(tick.offer),
                    "mid": float(tick.mid),
                }
            )
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json(
                {
                    "type": "stream_status",
                    "status": "failed",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "message": str(exc),
                }
            )
        except Exception:
            return


def _timeframe_seconds(timeframe: str) -> int:
    durations = {
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    if timeframe not in durations:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return durations[timeframe]


def _candle_start_time(value: datetime, duration_seconds: int) -> int:
    timestamp = int(value.astimezone(timezone.utc).timestamp())
    return timestamp - (timestamp % duration_seconds)


def _resolve_epic(symbol: str) -> str:
    if not symbol:
        raise ValueError("symbol is required")

    client = IGClient()
    base = symbol[:3]
    quote = symbol[3:6]
    for query in (f"{base}/{quote}", symbol):
        payload = client.search_markets(query)
        market = _choose_market(symbol, payload.get("markets", []))
        if market and market.get("epic"):
            return market["epic"]

    raise IGClientError(f"No IG market found for {symbol}")


def _choose_market(symbol: str, markets: list[dict[str, Any]]) -> dict[str, Any] | None:
    compact_symbol = symbol.upper()
    slash_symbol = f"{symbol[:3]}/{symbol[3:6]}".upper()
    for market in markets:
        normalized = _normalize_market_name(market)
        if slash_symbol in normalized:
            return market
    for market in markets:
        normalized = _normalize_market_name(market)
        if compact_symbol in normalized:
            return market
    return markets[0] if markets else None


def _normalize_market_name(market: dict[str, Any]) -> str:
    return " ".join(str(value) for value in (market.get("instrumentName"), market.get("marketName"), market.get("epic")) if value).upper()

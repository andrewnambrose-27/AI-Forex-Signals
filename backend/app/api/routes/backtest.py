from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.candle import Candle
from app.models.economic_event import EconomicEvent
from app.schemas.backtest import BacktestRequest, BacktestResponse, BacktestTradeRead
from app.services.backtesting import run_backtest
from app.services.ig_client import IGClient, IGClientError, parse_ig_candle

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("", response_model=BacktestResponse)
def create_backtest(payload: BacktestRequest, db: DbSession) -> BacktestResponse:
    primary = _load_candles(db, payload.epic, payload.timeframe, payload.limit)
    higher = _load_candles(db, payload.epic, _higher_timeframe(payload.timeframe), payload.limit)
    events = list(db.scalars(select(EconomicEvent).order_by(EconomicEvent.event_time.asc())))
    result = run_backtest(
        pair=payload.pair,
        timeframe=payload.timeframe,
        primary_candles=primary,
        higher_candles=higher,
        economic_events=events,
        minimum_score=payload.minimum_score,
        spread_points=payload.spread_points,
        slippage_points=payload.slippage_points,
    )
    return BacktestResponse(
        pair=payload.pair.upper(),
        epic=payload.epic,
        timeframe=payload.timeframe,
        assumptions={
            "minimum_score": payload.minimum_score,
            "spread_points": payload.spread_points,
            "slippage_points": payload.slippage_points,
            "entry": "next candle open after signal candle closes",
            "same_candle_stop_target": "stop first",
        },
        metrics=result.metrics,
        trades=[BacktestTradeRead(**trade.__dict__) for trade in result.trades],
        skipped_signals=result.skipped_signals,
        notes=[
            "Backtest uses closed candles only and enters on the next candle open to avoid lookahead bias.",
            "Results are historical simulations, not live-trading promises or guaranteed win probabilities.",
        ],
    )


def _load_candles(db: DbSession, epic: str, timeframe: str, limit: int) -> list[Candle]:
    resolution = _resolution_for_timeframe(timeframe)
    try:
        payload = IGClient().get_historical_prices(epic, resolution, limit)
    except IGClientError as exc:
        stored = _stored_candles(db, epic, resolution, limit)
        if stored:
            return stored
        raise HTTPException(status_code=exc.status_code, detail={"message": str(exc), "details": exc.details}) from exc

    candles: list[Candle] = []
    for raw_price in payload.get("prices", []):
        parsed = parse_ig_candle(raw_price, epic, resolution)
        if parsed is None:
            continue
        candles.append(_upsert_candle(db, parsed))
    db.commit()
    return sorted(candles or _stored_candles(db, epic, resolution, limit), key=lambda candle: candle.opened_at)


def _stored_candles(db: DbSession, epic: str, resolution: str, limit: int) -> list[Candle]:
    query = (
        select(Candle)
        .where(Candle.epic == epic, Candle.resolution == resolution, Candle.provider == "ig")
        .order_by(Candle.opened_at.desc())
        .limit(limit)
    )
    return sorted(db.scalars(query), key=lambda candle: candle.opened_at)


def _upsert_candle(db: DbSession, parsed: dict[str, Any]) -> Candle:
    existing = db.scalar(
        select(Candle).where(
            Candle.epic == parsed["epic"],
            Candle.resolution == parsed["resolution"],
            Candle.opened_at == parsed["opened_at"],
        )
    )
    if existing:
        for key, value in parsed.items():
            setattr(existing, key, value)
        return existing
    candle = Candle(**parsed)
    db.add(candle)
    return candle


def _higher_timeframe(timeframe: str) -> str:
    return {"5m": "15m", "15m": "1h", "1h": "4h", "4h": "1d", "1d": "1d"}.get(timeframe.lower(), "4h")


def _resolution_for_timeframe(timeframe: str) -> str:
    resolutions = {
        "5m": "MINUTE_5",
        "15m": "MINUTE_15",
        "1h": "HOUR",
        "4h": "HOUR_4",
        "1d": "DAY",
    }
    normalized = timeframe.lower()
    if normalized not in resolutions:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")
    return resolutions[normalized]

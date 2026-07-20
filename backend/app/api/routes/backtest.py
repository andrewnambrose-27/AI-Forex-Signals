from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.candle import Candle
from app.models.economic_event import EconomicEvent
from app.schemas.backtest import BacktestRequest, BacktestResponse, BacktestTradeRead
from app.services.backtesting import run_backtest
from app.api.routes.ig import fetch_candles
from app.services.multi_timeframe import TIMEFRAME_RELATIONSHIPS, required_timeframes

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("", response_model=BacktestResponse)
def create_backtest(payload: BacktestRequest, db: DbSession) -> BacktestResponse:
    timeframes = required_timeframes(payload.timeframe)
    candles_by_timeframe = {item: _load_candles(db, payload.epic, item, payload.limit) for item in timeframes}
    confirmation_timeframe, bias_timeframe = TIMEFRAME_RELATIONSHIPS[payload.timeframe.lower()]
    primary = candles_by_timeframe[payload.timeframe.lower()]
    higher = candles_by_timeframe.get(confirmation_timeframe) or candles_by_timeframe.get(bias_timeframe) or primary
    events = list(db.scalars(select(EconomicEvent).order_by(EconomicEvent.event_time.asc())))
    result = run_backtest(
        pair=payload.pair,
        timeframe=payload.timeframe,
        primary_candles=primary,
        higher_candles=higher,
        confirmation_candles=candles_by_timeframe.get(confirmation_timeframe),
        bias_candles=candles_by_timeframe.get(bias_timeframe),
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
            "multi_timeframe_close_rule": "higher-timeframe candle open plus duration must be at or before signal time",
        },
        metrics=result.metrics,
        trades=[BacktestTradeRead(**trade.__dict__) for trade in result.trades],
        skipped_signals=result.skipped_signals,
        notes=[
            "Backtest uses closed candles only and enters on the next candle open to avoid lookahead bias.",
            "Higher-timeframe confirmation uses only candles that had fully closed at each historical signal timestamp.",
            "Results are historical simulations, not live-trading promises or guaranteed win probabilities.",
        ],
    )


def _load_candles(db: DbSession, epic: str, timeframe: str, limit: int) -> list[Candle]:
    return fetch_candles(db=db, epic=epic, resolution=timeframe, limit=limit)["candles"]

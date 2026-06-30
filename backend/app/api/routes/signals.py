from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.candle import Candle
from app.models.signal import Signal
from app.schemas.signal import SignalComponentRead, SignalEvaluateRequest, SignalEvaluationRead, SignalRead, SignalRequest
from app.services.ig_client import IGClient, IGClientError, parse_ig_candle
from app.services.signal_engine import StrategyEvaluation, StrategyResult, evaluate_strategies, generate_signal

router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/score", response_model=SignalRead)
def score_signal(payload: SignalRequest) -> SignalRead:
    return generate_signal(payload)


@router.post("/evaluate", response_model=SignalEvaluationRead)
def evaluate_signal(payload: SignalEvaluateRequest, db: DbSession) -> SignalEvaluationRead:
    timeframes = _required_timeframes(payload.timeframe)
    candles_by_timeframe = {
        timeframe: _load_strategy_candles(db, payload.epic, timeframe, limit=300) for timeframe in timeframes
    }
    evaluation = evaluate_strategies(
        epic=payload.epic,
        pair=payload.pair,
        timeframe=payload.timeframe,
        minimum_score=payload.minimum_score,
        candles_by_timeframe=candles_by_timeframe,
    )
    return _evaluation_response(evaluation)


@router.get("/history", response_model=list[SignalRead])
def signal_history(db: DbSession, limit: int = 100) -> list[Signal]:
    query = select(Signal).order_by(Signal.created_at.desc()).limit(min(limit, 500))
    return list(db.scalars(query))


def _load_strategy_candles(db: DbSession, epic: str, timeframe: str, limit: int) -> list[Candle]:
    normalized_timeframe = timeframe.lower()
    resolution = _resolution_for_timeframe(normalized_timeframe)

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


def _required_timeframes(timeframe: str) -> list[str]:
    normalized = timeframe.lower()
    higher = {"5m": "15m", "15m": "1h", "1h": "4h", "4h": "1d", "1d": "1d"}.get(normalized, "4h")
    return [normalized] if normalized == higher else [normalized, higher]


def _resolution_for_timeframe(timeframe: str) -> str:
    resolutions = {
        "5m": "MINUTE_5",
        "15m": "MINUTE_15",
        "1h": "HOUR",
        "4h": "HOUR_4",
        "1d": "DAY",
    }
    if timeframe not in resolutions:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")
    return resolutions[timeframe]


def _evaluation_response(evaluation: StrategyEvaluation) -> SignalEvaluationRead:
    return SignalEvaluationRead(
        pair=evaluation.pair,
        epic=evaluation.epic,
        direction=evaluation.direction,
        timeframe=evaluation.timeframe,
        score=evaluation.score,
        status=evaluation.status,
        strategy=evaluation.strategy,
        entry_reference_price=evaluation.entry_reference_price,
        suggested_stop=evaluation.suggested_stop,
        suggested_target=evaluation.suggested_target,
        risk_reward_ratio=evaluation.risk_reward_ratio,
        reasons=evaluation.reasons,
        filters_passed=evaluation.filters_passed,
        filters_failed=evaluation.filters_failed,
        components=[_component_response(component) for component in evaluation.components],
    )


def _component_response(component: StrategyResult) -> SignalComponentRead:
    return SignalComponentRead(
        strategy=component.strategy,
        direction=component.direction,
        score=component.score,
        components=component.components,
        reasons=component.reasons,
        filters_passed=component.filters_passed,
        filters_failed=component.filters_failed,
    )

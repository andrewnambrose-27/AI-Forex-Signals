from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from statistics import mean
from typing import Any

from app.models.economic_event import EconomicEvent
from app.services.signal_engine import StrategyResult, evaluate_strategy_candidates
from app.services.signal_scoring import DEFAULT_SCORING_SETTINGS, apply_configurable_scoring
from app.services.multi_timeframe import TIMEFRAME_RELATIONSHIPS, analyze_multi_timeframe, candle_close_time, closed_candles_available_at


@dataclass(frozen=True)
class BacktestTrade:
    strategy: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    r_multiple: float
    hold_minutes: float
    session: str
    news_filtered_period: bool


@dataclass(frozen=True)
class BacktestResult:
    trades: list[BacktestTrade]
    skipped_signals: int
    metrics: dict[str, Any]


def run_backtest(
    *,
    pair: str,
    timeframe: str,
    primary_candles: list[Any],
    higher_candles: list[Any],
    confirmation_candles: list[Any] | None = None,
    bias_candles: list[Any] | None = None,
    economic_events: list[EconomicEvent],
    minimum_score: int,
    spread_points: float,
    slippage_points: float,
) -> BacktestResult:
    candles = sorted(primary_candles, key=lambda candle: candle.opened_at)
    confirmation_timeframe, bias_timeframe = TIMEFRAME_RELATIONSHIPS[timeframe.lower()]
    confirmation = sorted(confirmation_candles if confirmation_candles is not None else higher_candles, key=lambda candle: candle.opened_at)
    bias = sorted(bias_candles if bias_candles is not None else higher_candles, key=lambda candle: candle.opened_at)
    trades: list[BacktestTrade] = []
    skipped_signals = 0
    index = 80

    while index < len(candles) - 2:
        signal_time = candle_close_time(candles[index], timeframe.lower())
        primary_window = candles[: index + 2]
        confirmation_window = closed_candles_available_at(confirmation, confirmation_timeframe, signal_time) if confirmation_timeframe else []
        bias_window = closed_candles_available_at(bias, bias_timeframe, signal_time) if bias_timeframe else []
        strategy_higher = confirmation_window or bias_window
        if len(strategy_higher) < 61:
            index += 1
            continue

        candidates = [
            candidate
            for candidate in evaluate_strategy_candidates(primary_window, [*strategy_higher, strategy_higher[-1]])
            if candidate.direction in {"BUY", "SELL"}
        ]
        if not candidates:
            index += 1
            continue

        for candidate in candidates:
            timeframe_candles = {timeframe.lower(): candles[: index + 1]}
            if confirmation_timeframe:
                timeframe_candles[confirmation_timeframe] = confirmation_window
            if bias_timeframe:
                timeframe_candles[bias_timeframe] = bias_window
            multi_timeframe = analyze_multi_timeframe(
                timeframe_candles,
                entry_timeframe=timeframe,
                signal_direction=candidate.direction,
            )
            scored = apply_configurable_scoring(
                _evaluation_stub(pair, timeframe, candidate),
                settings=DEFAULT_SCORING_SETTINGS,
                minimum_score_override=minimum_score,
                news_blocked=_in_news_window(signal_time, pair, economic_events),
                multi_timeframe_penalty=multi_timeframe.score_penalty,
                multi_timeframe_details=multi_timeframe.reasons[-1],
            )
            if multi_timeframe.strong_conflict or scored.score < minimum_score:
                skipped_signals += 1
                continue
            trade = _simulate_trade(
                strategy=candidate,
                candles=candles,
                entry_index=index + 1,
                spread_points=spread_points,
                slippage_points=slippage_points,
                news_filtered_period=_in_news_window(signal_time, pair, economic_events),
            )
            if trade is not None:
                trades.append(trade)
                index = max(index + 1, _find_candle_index(candles, trade.exit_time))
                break
        else:
            index += 1
            continue
        index += 1

    return BacktestResult(trades=trades, skipped_signals=skipped_signals, metrics=_metrics(trades))


def _simulate_trade(
    *,
    strategy: StrategyResult,
    candles: list[Any],
    entry_index: int,
    spread_points: float,
    slippage_points: float,
    news_filtered_period: bool,
) -> BacktestTrade | None:
    if strategy.suggested_stop is None or strategy.suggested_target is None:
        return None
    entry_candle = candles[entry_index]
    direction = strategy.direction
    cost = spread_points + slippage_points
    raw_entry = float(entry_candle.open)
    entry = raw_entry + cost if direction == "BUY" else raw_entry - cost
    stop = float(strategy.suggested_stop)
    target = float(strategy.suggested_target)
    risk = abs(entry - stop)
    if risk <= 0 or not isfinite(risk):
        return None

    for exit_index in range(entry_index, len(candles)):
        candle = candles[exit_index]
        high = float(candle.high)
        low = float(candle.low)
        if direction == "BUY":
            stop_hit = low <= stop
            target_hit = high >= target
            if stop_hit:
                exit_price = stop - slippage_points
                r_multiple = (exit_price - entry) / risk
                return _trade(strategy, entry_candle, candle, entry, exit_price, stop, target, r_multiple, news_filtered_period)
            if target_hit:
                exit_price = target - slippage_points
                r_multiple = (exit_price - entry) / risk
                return _trade(strategy, entry_candle, candle, entry, exit_price, stop, target, r_multiple, news_filtered_period)
        else:
            stop_hit = high >= stop
            target_hit = low <= target
            if stop_hit:
                exit_price = stop + slippage_points
                r_multiple = (entry - exit_price) / risk
                return _trade(strategy, entry_candle, candle, entry, exit_price, stop, target, r_multiple, news_filtered_period)
            if target_hit:
                exit_price = target + slippage_points
                r_multiple = (entry - exit_price) / risk
                return _trade(strategy, entry_candle, candle, entry, exit_price, stop, target, r_multiple, news_filtered_period)

    last = candles[-1]
    exit_price = float(last.close)
    r_multiple = ((exit_price - entry) / risk) if direction == "BUY" else ((entry - exit_price) / risk)
    return _trade(strategy, entry_candle, last, entry, exit_price, stop, target, r_multiple, news_filtered_period)


def _trade(
    strategy: StrategyResult,
    entry_candle: Any,
    exit_candle: Any,
    entry: float,
    exit_price: float,
    stop: float,
    target: float,
    r_multiple: float,
    news_filtered_period: bool,
) -> BacktestTrade:
    entry_time = _aware(entry_candle.opened_at)
    exit_time = _aware(exit_candle.opened_at)
    return BacktestTrade(
        strategy=strategy.strategy,
        direction=strategy.direction,
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=round(entry, 8),
        exit_price=round(exit_price, 8),
        stop_loss=round(stop, 8),
        take_profit=round(target, 8),
        r_multiple=round(r_multiple, 4),
        hold_minutes=max(0, (exit_time - entry_time).total_seconds() / 60),
        session=_session(entry_time),
        news_filtered_period=news_filtered_period,
    )


def _metrics(trades: list[BacktestTrade]) -> dict[str, Any]:
    if not trades:
        return {
            "win_rate": 0,
            "average_r": 0,
            "max_drawdown": 0,
            "profit_factor": 0,
            "number_of_trades": 0,
            "average_hold_time_minutes": 0,
            "performance_by_session": {},
            "performance_around_news_filtered_periods": {"trades": 0, "average_r": 0},
        }

    wins = [trade for trade in trades if trade.r_multiple > 0]
    gross_profit = sum(trade.r_multiple for trade in trades if trade.r_multiple > 0)
    gross_loss = abs(sum(trade.r_multiple for trade in trades if trade.r_multiple < 0))
    sessions: dict[str, list[float]] = {}
    for trade in trades:
        sessions.setdefault(trade.session, []).append(trade.r_multiple)
    news_trades = [trade.r_multiple for trade in trades if trade.news_filtered_period]

    return {
        "win_rate": round((len(wins) / len(trades)) * 100, 2),
        "average_r": round(mean(trade.r_multiple for trade in trades), 4),
        "max_drawdown": round(_max_drawdown([trade.r_multiple for trade in trades]), 4),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else round(gross_profit, 4),
        "number_of_trades": len(trades),
        "average_hold_time_minutes": round(mean(trade.hold_minutes for trade in trades), 2),
        "performance_by_session": {
            session: {"trades": len(values), "average_r": round(mean(values), 4), "total_r": round(sum(values), 4)}
            for session, values in sessions.items()
        },
        "performance_around_news_filtered_periods": {
            "trades": len(news_trades),
            "average_r": round(mean(news_trades), 4) if news_trades else 0,
            "total_r": round(sum(news_trades), 4),
        },
    }


def _max_drawdown(r_values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in r_values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return abs(max_drawdown)


def _session(value: datetime) -> str:
    hour = value.hour
    if 7 <= hour < 12:
        return "london"
    if 12 <= hour < 17:
        return "new_york_overlap"
    if 17 <= hour < 22:
        return "new_york"
    if 22 <= hour or hour < 7:
        return "asia"
    return "other"


def _in_news_window(value: datetime, pair: str, events: list[EconomicEvent]) -> bool:
    currencies = {pair[:3].upper(), pair[3:6].upper()}
    current = _aware(value)
    for event in events:
        if event.currency.upper() not in currencies or event.impact.lower() != "high":
            continue
        event_time = _aware(event.event_time)
        if event_time - timedelta(minutes=60) <= current <= event_time + timedelta(minutes=30):
            return True
    return False


def _find_candle_index(candles: list[Any], opened_at: datetime) -> int:
    for index, candle in enumerate(candles):
        if _aware(candle.opened_at) >= opened_at:
            return index
    return len(candles) - 1


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _evaluation_stub(pair: str, timeframe: str, strategy: StrategyResult) -> Any:
    return type(
        "EvaluationStub",
        (),
        {
            "pair": pair,
            "timeframe": timeframe,
            "strategy": strategy.strategy,
            "components": [strategy],
        },
    )()

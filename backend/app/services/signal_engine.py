from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.schemas.signal import SignalRead, SignalRequest
from app.services.technical_indicators import adx, atr, bollinger_bands, ema_set, macd, rsi, support_resistance_zones


@dataclass(frozen=True)
class StrategyCandle:
    open: float
    high: float
    low: float
    close: float


@dataclass
class StrategyResult:
    strategy: str
    direction: str = "NONE"
    score: int = 0
    components: dict[str, int | float | str | bool | None] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    filters_passed: list[str] = field(default_factory=list)
    filters_failed: list[str] = field(default_factory=list)
    entry_reference_price: Decimal | None = None
    suggested_stop: Decimal | None = None
    suggested_target: Decimal | None = None
    risk_reward_ratio: Decimal | None = None


@dataclass
class StrategyEvaluation:
    pair: str
    epic: str
    timeframe: str
    direction: str
    score: int
    status: str
    strategy: str | None
    entry_reference_price: Decimal | None
    suggested_stop: Decimal | None
    suggested_target: Decimal | None
    risk_reward_ratio: Decimal | None
    reasons: list[str]
    filters_passed: list[str]
    filters_failed: list[str]
    components: list[StrategyResult]
    score_components: list[Any] = field(default_factory=list)


def generate_signal(payload: SignalRequest) -> SignalRead:
    symbol = payload.symbol.upper()
    return SignalRead(
        pair=symbol,
        direction="NONE",
        timeframe=payload.timeframe,
        score=0,
        status="filtered",
        reasons=["Use /api/signals/evaluate for strategy-based signals. No trades are placed by this application."],
        filters_passed=["signal_only_mode"],
        filters_failed=["strategy_input_missing"],
    )


def evaluate_strategies(
    *,
    epic: str,
    pair: str,
    timeframe: str,
    minimum_score: int,
    candles_by_timeframe: dict[str, list[Any]],
) -> StrategyEvaluation:
    normalized_timeframe = timeframe.lower()
    primary = _closed_candles(candles_by_timeframe.get(normalized_timeframe, []))
    higher_timeframe = _higher_timeframe(normalized_timeframe)
    higher = _closed_candles(candles_by_timeframe.get(higher_timeframe, []))
    filters_passed = ["signal_only_mode", "closed_candles_only", "non_repainting_rules"]
    filters_failed: list[str] = []

    if len(primary) < 60:
        filters_failed.append("not_enough_closed_primary_candles")
    if len(higher) < 60:
        filters_failed.append("not_enough_closed_higher_timeframe_candles")

    if filters_failed:
        return StrategyEvaluation(
            pair=pair.upper(),
            epic=epic,
            timeframe=normalized_timeframe,
            direction="NONE",
            score=0,
            status="filtered",
            strategy=None,
            entry_reference_price=None,
            suggested_stop=None,
            suggested_target=None,
            risk_reward_ratio=None,
            reasons=["Not enough closed candle history to evaluate strategies without repainting."],
            filters_passed=filters_passed,
            filters_failed=filters_failed,
            components=[],
        )

    results = [
        _trend_continuation(primary, higher),
        _breakout_volatility_expansion(primary, higher),
        _range_mean_reversion(primary, higher),
    ]
    candidates = [result for result in results if result.direction in {"BUY", "SELL"}]
    best = max(candidates, key=lambda result: result.score, default=None)

    if best is None or best.score < minimum_score:
        score = best.score if best else 0
        reasons = [best.reasons[0]] if best and best.reasons else ["No strategy met the current signal rules."]
        return StrategyEvaluation(
            pair=pair.upper(),
            epic=epic,
            timeframe=normalized_timeframe,
            direction="NONE",
            score=score,
            status="filtered",
            strategy=best.strategy if best else None,
            entry_reference_price=best.entry_reference_price if best else None,
            suggested_stop=best.suggested_stop if best else None,
            suggested_target=best.suggested_target if best else None,
            risk_reward_ratio=best.risk_reward_ratio if best else None,
            reasons=reasons,
            filters_passed=filters_passed,
            filters_failed=[*filters_failed, "minimum_score_not_met"],
            components=results,
        )

    return StrategyEvaluation(
        pair=pair.upper(),
        epic=epic,
        timeframe=normalized_timeframe,
        direction=best.direction,
        score=best.score,
        status="active",
        strategy=best.strategy,
        entry_reference_price=best.entry_reference_price,
        suggested_stop=best.suggested_stop,
        suggested_target=best.suggested_target,
        risk_reward_ratio=best.risk_reward_ratio,
        reasons=best.reasons,
        filters_passed=[*filters_passed, *best.filters_passed],
        filters_failed=[*filters_failed, *best.filters_failed],
        components=results,
    )


def _trend_continuation(primary: list[StrategyCandle], higher: list[StrategyCandle]) -> StrategyResult:
    strategy = "trend_continuation"
    primary_emas = ema_set(primary)
    higher_emas = ema_set(higher)
    primary_macd = macd(primary)
    primary_adx = adx(primary)
    primary_atr = atr(primary)
    last = primary[-1]
    previous = primary[-2]
    ema20 = _last(primary_emas["ema_20"])
    ema50 = _last(primary_emas["ema_50"])
    ema200 = _last(primary_emas["ema_200"])
    higher_ema20 = _last(higher_emas["ema_20"])
    higher_ema50 = _last(higher_emas["ema_50"])
    higher_ema200 = _last(higher_emas["ema_200"])
    macd_hist = _last(primary_macd["histogram"])
    adx_value = _last(primary_adx["adx"]) or 0
    atr_value = _last(primary_atr) or max(last.high - last.low, 0.0001)

    if None in {ema20, ema50, ema200, higher_ema20, higher_ema50, higher_ema200, macd_hist}:
        return _no_signal(strategy, "Trend continuation needs more EMA/MACD history.")

    bullish_stack = higher_ema20 > higher_ema50 > higher_ema200 and ema20 > ema50 > ema200
    bearish_stack = higher_ema20 < higher_ema50 < higher_ema200 and ema20 < ema50 < ema200
    pullback_buy = previous.close <= ema20 and last.close > ema20
    pullback_sell = previous.close >= ema20 and last.close < ema20
    direction = "BUY" if bullish_stack and pullback_buy and macd_hist > 0 else "SELL" if bearish_stack and pullback_sell and macd_hist < 0 else "NONE"
    if direction == "NONE":
        return StrategyResult(
            strategy=strategy,
            direction="NONE",
            score=0,
            components={"ema_alignment": int(bullish_stack or bearish_stack), "adx": round(adx_value, 2), "macd_histogram": round(macd_hist, 6)},
            reasons=["Trend continuation is waiting for aligned EMAs plus a closed-candle pullback reclaim."],
            filters_failed=["trend_alignment_or_pullback_missing"],
        )

    score = _clamp_score(35 + (25 if bullish_stack or bearish_stack else 0) + (20 if adx_value >= 18 else 8) + (15 if abs(macd_hist) > 0 else 0))
    return _with_risk(
        StrategyResult(
            strategy=strategy,
            direction=direction,
            score=score,
            components={"ema_alignment": 25, "adx": round(adx_value, 2), "macd_histogram": round(macd_hist, 6), "pullback_reclaim": 20},
            reasons=[
                f"{direction} trend continuation: closed candle reclaimed EMA 20 with multi-timeframe EMA alignment.",
                f"ADX is {adx_value:.1f}, so trend strength is {'acceptable' if adx_value >= 18 else 'modest'}.",
            ],
            filters_passed=["multi_timeframe_ema_alignment", "closed_candle_pullback_reclaim"],
        ),
        last,
        atr_value,
    )


def _breakout_volatility_expansion(primary: list[StrategyCandle], higher: list[StrategyCandle]) -> StrategyResult:
    strategy = "breakout_volatility_expansion"
    last = primary[-1]
    previous_window = primary[-31:-1]
    recent_high = max(candle.high for candle in previous_window)
    recent_low = min(candle.low for candle in previous_window)
    atr_values = atr(primary)
    bands = bollinger_bands(primary)
    current_atr = _last(atr_values) or 0
    prior_atr_values = [value for value in atr_values[-21:-1] if value is not None]
    average_prior_atr = sum(prior_atr_values) / len(prior_atr_values) if prior_atr_values else current_atr
    upper = _last(bands["upper"])
    lower = _last(bands["lower"])
    middle = _last(bands["middle"])
    width = (upper - lower) if upper is not None and lower is not None else 0
    width_percent = width / middle if middle else 0
    higher_emas = ema_set(higher)
    higher_ema20 = _last(higher_emas["ema_20"])
    higher_ema50 = _last(higher_emas["ema_50"])
    higher_bias_buy = higher_ema20 is not None and higher_ema50 is not None and higher_ema20 >= higher_ema50
    higher_bias_sell = higher_ema20 is not None and higher_ema50 is not None and higher_ema20 <= higher_ema50

    buy_breakout = last.close > recent_high and current_atr > average_prior_atr * 1.05 and higher_bias_buy
    sell_breakout = last.close < recent_low and current_atr > average_prior_atr * 1.05 and higher_bias_sell
    direction = "BUY" if buy_breakout else "SELL" if sell_breakout else "NONE"
    if direction == "NONE":
        return StrategyResult(
            strategy=strategy,
            direction="NONE",
            score=0,
            components={"recent_high": recent_high, "recent_low": recent_low, "atr_expanding": current_atr > average_prior_atr * 1.05, "bb_width_percent": round(width_percent, 5)},
            reasons=["Breakout strategy needs a closed candle beyond the recent range with ATR expansion."],
            filters_failed=["breakout_or_volatility_expansion_missing"],
        )

    score = _clamp_score(45 + (25 if current_atr > average_prior_atr * 1.05 else 0) + (15 if width_percent > 0 else 0) + 10)
    return _with_risk(
        StrategyResult(
            strategy=strategy,
            direction=direction,
            score=score,
            components={"range_break": 30, "atr_expansion": round(current_atr / average_prior_atr, 3) if average_prior_atr else None, "bb_width_percent": round(width_percent, 5)},
            reasons=[
                f"{direction} breakout: the last closed candle broke the prior 30-candle range.",
                "ATR is expanding, which supports volatility continuation.",
            ],
            filters_passed=["closed_candle_range_break", "atr_expansion"],
        ),
        last,
        current_atr,
        reward_multiple=2.2,
    )


def _range_mean_reversion(primary: list[StrategyCandle], higher: list[StrategyCandle]) -> StrategyResult:
    strategy = "range_mean_reversion"
    last = primary[-1]
    rsi_values = rsi(primary)
    adx_values = adx(primary)
    bands = bollinger_bands(primary)
    zones = support_resistance_zones(primary[-120:], lookback=3, tolerance_percent=0.08, min_touches=2)
    rsi_value = _last(rsi_values)
    adx_value = _last(adx_values["adx"]) or 100
    lower_band = _last(bands["lower"])
    upper_band = _last(bands["upper"])
    support = _nearest_zone(last.close, zones["support"])
    resistance = _nearest_zone(last.close, zones["resistance"])
    near_support = support is not None and abs(last.close - support) <= max(last.close * 0.001, last.high - last.low)
    near_resistance = resistance is not None and abs(last.close - resistance) <= max(last.close * 0.001, last.high - last.low)

    buy_reversion = adx_value < 22 and rsi_value is not None and rsi_value <= 38 and lower_band is not None and last.close <= lower_band * 1.002 and near_support
    sell_reversion = adx_value < 22 and rsi_value is not None and rsi_value >= 62 and upper_band is not None and last.close >= upper_band * 0.998 and near_resistance
    direction = "BUY" if buy_reversion else "SELL" if sell_reversion else "NONE"
    if direction == "NONE":
        return StrategyResult(
            strategy=strategy,
            direction="NONE",
            score=0,
            components={"rsi": round(rsi_value, 2) if rsi_value is not None else None, "adx": round(adx_value, 2), "near_support": near_support, "near_resistance": near_resistance},
            reasons=["Range mean reversion needs low ADX, an extreme RSI reading, and price near a pivot zone."],
            filters_failed=["range_reversion_conditions_missing"],
        )

    atr_value = _last(atr(primary)) or max(last.high - last.low, 0.0001)
    score = _clamp_score(40 + (20 if adx_value < 22 else 0) + (20 if near_support or near_resistance else 0) + 10)
    return _with_risk(
        StrategyResult(
            strategy=strategy,
            direction=direction,
            score=score,
            components={"rsi": round(rsi_value, 2) if rsi_value is not None else None, "adx": round(adx_value, 2), "pivot_zone_confirmed": True},
            reasons=[
                f"{direction} range mean reversion: closed candle is near a pivot zone while RSI is stretched.",
                f"ADX is {adx_value:.1f}, suggesting range conditions rather than a strong trend.",
            ],
            filters_passed=["low_adx_range_condition", "pivot_zone_reversion"],
        ),
        last,
        atr_value,
        reward_multiple=1.5,
    )


def _closed_candles(candles: list[Any]) -> list[StrategyCandle]:
    normalized = [
        StrategyCandle(open=float(candle.open), high=float(candle.high), low=float(candle.low), close=float(candle.close))
        for candle in candles
    ]
    return normalized[:-1]


def _higher_timeframe(timeframe: str) -> str:
    mapping = {"5m": "15m", "15m": "1h", "1h": "4h", "4h": "1d", "1d": "1d"}
    return mapping.get(timeframe, "4h")


def _last(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _nearest_zone(price: float, zones: list[dict[str, float | int]]) -> float | None:
    if not zones:
        return None
    return float(min(zones, key=lambda zone: abs(float(zone["price"]) - price))["price"])


def _with_risk(result: StrategyResult, candle: StrategyCandle, atr_value: float, reward_multiple: float = 2.0) -> StrategyResult:
    entry = Decimal(str(round(candle.close, 8)))
    risk_distance = Decimal(str(round(max(atr_value * 1.2, candle.close * 0.001), 8)))
    reward_distance = risk_distance * Decimal(str(reward_multiple))
    if result.direction == "BUY":
        result.suggested_stop = entry - risk_distance
        result.suggested_target = entry + reward_distance
    else:
        result.suggested_stop = entry + risk_distance
        result.suggested_target = entry - reward_distance
    result.entry_reference_price = entry
    result.risk_reward_ratio = Decimal(str(reward_multiple))
    return result


def _no_signal(strategy: str, reason: str) -> StrategyResult:
    return StrategyResult(strategy=strategy, direction="NONE", score=0, reasons=[reason], filters_failed=["insufficient_indicator_history"])


def _clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))

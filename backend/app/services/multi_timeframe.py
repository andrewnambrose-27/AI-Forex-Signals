from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.services.market_structure import analyze_market_structure
from app.services.support_resistance import detect_support_resistance_zones
from app.services.technical_indicators import adx, ema_set


TimeframeDirection = Literal["bullish", "bearish", "neutral", "insufficient_data"]
AlignmentResult = Literal["aligned", "mixed", "conflicting"]
TrendStrength = Literal["strong", "moderate", "weak", "insufficient_data"]

TIMEFRAME_RELATIONSHIPS: dict[str, tuple[str | None, str | None]] = {
    "5m": ("15m", "1h"),
    "15m": ("1h", "4h"),
    "1h": ("4h", "1d"),
    "4h": (None, "1d"),
    "1d": (None, None),
}

TIMEFRAME_DURATIONS = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


@dataclass(frozen=True)
class TimeframeState:
    timeframe: str
    role: Literal["entry", "confirmation", "directional_bias"]
    direction: TimeframeDirection
    ema_alignment: Literal["bullish", "bearish", "neutral", "insufficient_data"]
    market_structure: str
    adx: float | None
    trend_strength: TrendStrength
    support_zones: int
    resistance_zones: int
    zone_context: Literal["support_nearby", "resistance_nearby", "balanced", "none"]
    recent_structure_break: Literal["bullish", "bearish", "none"]
    confidence_score: int
    closed_candle_count: int
    latest_closed_at: datetime | None
    reasons: list[str]


@dataclass(frozen=True)
class MultiTimeframeAnalysis:
    entry_timeframe: str
    confirmation_timeframe: str | None
    directional_bias_timeframe: str | None
    entry_state: TimeframeState
    confirmation_state: TimeframeState | None
    higher_timeframe_state: TimeframeState | None
    result: AlignmentResult
    overall_direction: TimeframeDirection
    overall_summary: str
    score_penalty: int
    strong_conflict: bool
    reasons: list[str]


def required_timeframes(entry_timeframe: str) -> list[str]:
    normalized = entry_timeframe.lower()
    if normalized not in TIMEFRAME_RELATIONSHIPS:
        raise ValueError(f"Unsupported timeframe: {entry_timeframe}")
    confirmation, bias = TIMEFRAME_RELATIONSHIPS[normalized]
    return list(dict.fromkeys(value for value in (normalized, confirmation, bias) if value is not None))


def analyze_multi_timeframe(
    candles_by_timeframe: dict[str, list[Any]],
    *,
    entry_timeframe: str,
    signal_direction: str | None = None,
) -> MultiTimeframeAnalysis:
    entry = entry_timeframe.lower()
    if entry not in TIMEFRAME_RELATIONSHIPS:
        raise ValueError(f"Unsupported timeframe: {entry_timeframe}")
    confirmation, bias = TIMEFRAME_RELATIONSHIPS[entry]
    entry_state = analyze_timeframe_state(candles_by_timeframe.get(entry, []), timeframe=entry, role="entry")
    confirmation_state = (
        analyze_timeframe_state(candles_by_timeframe.get(confirmation, []), timeframe=confirmation, role="confirmation")
        if confirmation else None
    )
    bias_state = (
        analyze_timeframe_state(candles_by_timeframe.get(bias, []), timeframe=bias, role="directional_bias")
        if bias else None
    )
    states = [state for state in (entry_state, confirmation_state, bias_state) if state is not None]
    directional = [state.direction for state in states if state.direction in {"bullish", "bearish"}]
    unique = set(directional)
    if len(unique) > 1:
        result: AlignmentResult = "conflicting"
    elif len(directional) == len(states) and directional:
        result = "aligned"
    else:
        result = "mixed"

    bullish_weight = sum(_state_weight(state) for state in states if state.direction == "bullish")
    bearish_weight = sum(_state_weight(state) for state in states if state.direction == "bearish")
    if bullish_weight == bearish_weight:
        overall: TimeframeDirection = "neutral" if states else "insufficient_data"
    else:
        overall = "bullish" if bullish_weight > bearish_weight else "bearish"
    magnitude = abs(bullish_weight - bearish_weight)
    qualifier = "strongly" if magnitude >= 5 and result == "aligned" else "moderately" if magnitude >= 2 else "slightly"
    summary = f"{qualifier} {overall}" if overall in {"bullish", "bearish"} else "neutral"

    requested = "bullish" if signal_direction == "BUY" else "bearish" if signal_direction == "SELL" else None
    strong_conflict = bool(
        requested
        and bias_state
        and bias_state.direction not in {requested, "neutral", "insufficient_data"}
        and bias_state.trend_strength == "strong"
        and bias_state.confidence_score >= 65
    )
    penalty = 20 if strong_conflict else 12 if result == "conflicting" else 5 if result == "mixed" else 0
    reasons = [_alignment_reason(states)]
    if strong_conflict and bias_state and requested:
        action = "buy" if requested == "bullish" else "sell"
        reasons.append(f"Signal filtered because the {entry} {action} conflicts with a strong {bias_state.timeframe} {bias_state.direction} trend.")
    elif penalty:
        reasons.append(f"Signal quality reduced by {penalty} points because timeframe confirmation is {result}.")
    else:
        reasons.append("Entry, confirmation, and directional-bias timeframes are aligned.")
    return MultiTimeframeAnalysis(
        entry_timeframe=entry,
        confirmation_timeframe=confirmation,
        directional_bias_timeframe=bias,
        entry_state=entry_state,
        confirmation_state=confirmation_state,
        higher_timeframe_state=bias_state,
        result=result,
        overall_direction=overall,
        overall_summary=summary,
        score_penalty=penalty,
        strong_conflict=strong_conflict,
        reasons=reasons,
    )


def analyze_timeframe_state(candles: list[Any], *, timeframe: str, role: str) -> TimeframeState:
    closed = sorted((candle for candle in candles if _is_closed(candle)), key=lambda candle: _time(candle))
    latest_closed_at = candle_close_time(closed[-1], timeframe) if closed else None
    if len(closed) < 20:
        return TimeframeState(
            timeframe=timeframe, role=role, direction="insufficient_data", ema_alignment="insufficient_data",
            market_structure="insufficient_data", adx=None, trend_strength="insufficient_data", support_zones=0,
            resistance_zones=0, zone_context="none", recent_structure_break="none", confidence_score=0,
            closed_candle_count=len(closed), latest_closed_at=latest_closed_at,
            reasons=[f"{timeframe} needs more closed candles for multi-timeframe analysis."],
        )

    emas = ema_set(closed)
    ema20, ema50, ema200 = (_last(emas[name]) for name in ("ema_20", "ema_50", "ema_200"))
    if None in {ema20, ema50, ema200}:
        ema_direction = "insufficient_data"
    elif ema20 > ema50 > ema200:
        ema_direction = "bullish"
    elif ema20 < ema50 < ema200:
        ema_direction = "bearish"
    else:
        ema_direction = "neutral"

    structure = analyze_market_structure(closed, recent_limit=20)
    adx_values = adx(closed)["adx"]
    adx_value = _last(adx_values)
    strength: TrendStrength = "insufficient_data" if adx_value is None else "strong" if adx_value >= 25 else "moderate" if adx_value >= 18 else "weak"
    zones = detect_support_resistance_zones(closed, max_zones=8)
    active_support = [zone for zone in zones.zones if not zone.broken and zone.type in {"support", "mixed"}]
    active_resistance = [zone for zone in zones.zones if not zone.broken and zone.type in {"resistance", "mixed"}]
    price = float(_read(closed[-1], "close"))
    atr_value = zones.atr_14 or max(price * 0.001, 1e-12)
    near_support = any(_zone_distance(price, zone.lower_price, zone.upper_price) <= atr_value * 0.5 for zone in active_support)
    near_resistance = any(_zone_distance(price, zone.lower_price, zone.upper_price) <= atr_value * 0.5 for zone in active_resistance)
    zone_context = "balanced" if near_support and near_resistance else "support_nearby" if near_support else "resistance_nearby" if near_resistance else "none"
    recent_break = _recent_structure_break(structure.recent_structure_points, closed)

    vote = 0
    vote += 2 if ema_direction == "bullish" else -2 if ema_direction == "bearish" else 0
    vote += 2 if structure.direction == "bullish" else -2 if structure.direction == "bearish" else 0
    vote += 1 if recent_break == "bullish" else -1 if recent_break == "bearish" else 0
    direction: TimeframeDirection = "bullish" if vote >= 2 else "bearish" if vote <= -2 else "neutral"
    evidence = sum(value not in {"neutral", "insufficient_data", "none"} for value in (ema_direction, structure.direction, recent_break))
    confidence = min(100, 35 + evidence * 15 + (15 if strength == "strong" else 8 if strength == "moderate" else 0))
    reasons = [
        f"{timeframe} EMA alignment is {ema_direction}; confirmed structure is {structure.direction}.",
        f"{timeframe} ADX is {adx_value:.1f} ({strength}) and the recent structure break is {recent_break}." if adx_value is not None else f"{timeframe} ADX is still warming up.",
        f"{timeframe} has {len(active_support)} active support and {len(active_resistance)} active resistance zone(s).",
    ]
    return TimeframeState(
        timeframe=timeframe, role=role, direction=direction, ema_alignment=ema_direction,
        market_structure=structure.direction, adx=round(adx_value, 2) if adx_value is not None else None,
        trend_strength=strength, support_zones=len(active_support), resistance_zones=len(active_resistance),
        zone_context=zone_context, recent_structure_break=recent_break, confidence_score=confidence,
        closed_candle_count=len(closed), latest_closed_at=latest_closed_at, reasons=reasons,
    )


def closed_candles_available_at(candles: list[Any], timeframe: str, timestamp: datetime) -> list[Any]:
    cutoff = _aware(timestamp)
    return [candle for candle in sorted(candles, key=_time) if candle_close_time(candle, timeframe) <= cutoff and _is_closed(candle)]


def candle_close_time(candle: Any, timeframe: str) -> datetime:
    if timeframe not in TIMEFRAME_DURATIONS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return _aware(_time(candle)) + TIMEFRAME_DURATIONS[timeframe]


def _recent_structure_break(points: list[Any], candles: list[Any]) -> Literal["bullish", "bearish", "none"]:
    if not points:
        return "none"
    recent_times = {_time(candle) for candle in candles[-12:]}
    for point in reversed(points):
        if _aware(point.confirmed_at) not in recent_times:
            continue
        if point.classification == "HH":
            return "bullish"
        if point.classification == "LL":
            return "bearish"
    return "none"


def _alignment_reason(states: list[TimeframeState]) -> str:
    if len(states) == 3 and states[0].direction == states[1].direction and states[0].direction in {"bullish", "bearish"}:
        if states[2].direction == "neutral":
            return f"{states[0].timeframe} and {states[1].timeframe} structure are {states[0].direction}; {states[2].timeframe} remains neutral."
        if states[2].direction == states[0].direction:
            return f"{states[0].timeframe}, {states[1].timeframe}, and {states[2].timeframe} structure are {states[0].direction}."
    parts = [f"{state.timeframe} {state.direction}" for state in states]
    return f"{', '.join(parts[:-1])}; {parts[-1]}." if len(parts) > 1 else f"{parts[0].capitalize()}."


def _state_weight(state: TimeframeState) -> int:
    role_weight = 3 if state.role == "directional_bias" else 2 if state.role == "confirmation" else 1
    return role_weight + (1 if state.trend_strength == "strong" else 0)


def _zone_distance(price: float, lower: float, upper: float) -> float:
    return 0.0 if lower <= price <= upper else min(abs(price - lower), abs(price - upper))


def _last(values: list[float | None]) -> float | None:
    return next((value for value in reversed(values) if value is not None), None)


def _time(candle: Any) -> datetime:
    return _read(candle, "opened_at", "time")


def _read(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    raise ValueError(f"Value is missing required field: {' or '.join(names)}")


def _is_closed(candle: Any) -> bool:
    for name in ("is_closed", "isClosed"):
        if isinstance(candle, dict) and name in candle:
            return bool(candle[name])
        if hasattr(candle, name):
            return bool(getattr(candle, name))
    return True


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

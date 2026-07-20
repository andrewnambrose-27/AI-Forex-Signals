from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from statistics import mean
from typing import Any, Literal

from app.services.market_structure import StructurePoint, analyze_market_structure
from app.services.support_resistance import PriceZone
from app.services.technical_indicators import atr


TrendDirection = Literal["bullish", "bearish"]
TrendStatus = Literal["active", "broken"]
TrendRole = Literal["primary", "secondary"]


@dataclass(frozen=True)
class TrendLine:
    start_time: datetime
    start_price: float
    end_time: datetime
    end_price: float
    direction: TrendDirection
    role: TrendRole
    touch_count: int
    confidence_score: int
    status: TrendStatus
    broken_at: datetime | None
    bounce_detected: bool
    bounce_at: datetime | None
    break_retested: bool
    retested_at: datetime | None
    failed_retest: bool
    horizontal_zone_confluence: bool
    first_anchor_confirmed_at: datetime
    last_anchor_confirmed_at: datetime


@dataclass(frozen=True)
class TrendLineAnalysis:
    lines: list[TrendLine]
    atr_14: float | None
    touch_tolerance_atr: float
    break_buffer_atr: float
    minimum_anchor_distance: int
    closed_candle_count: int
    reasons: list[str]


@dataclass(frozen=True)
class _Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class _Candidate:
    first: StructurePoint
    second: StructurePoint
    direction: TrendDirection
    slope: float


def detect_trend_lines(
    candles: list[Any],
    *,
    left_candles: int = 3,
    right_candles: int = 3,
    minimum_anchor_distance: int = 5,
    touch_tolerance_atr: float = 0.25,
    break_buffer_atr: float = 0.1,
    violation_buffer_atr: float = 0.5,
    horizontal_zones: list[PriceZone] | None = None,
    max_lines: int = 3,
) -> TrendLineAnalysis:
    """Return a bounded set of trend lines derived from confirmed HL/LH pivots.

    Candidate formation and every subsequent event use closed candles only. A
    line cannot be acted upon before its second anchor's right-side pivot window
    has closed, which keeps walk-forward and batch calculations equivalent.
    """
    if minimum_anchor_distance < 1:
        raise ValueError("minimum_anchor_distance must be at least 1")
    if touch_tolerance_atr <= 0:
        raise ValueError("touch_tolerance_atr must be greater than zero")
    if break_buffer_atr < 0 or violation_buffer_atr < 0:
        raise ValueError("ATR buffers cannot be negative")
    if not 1 <= max_lines <= 3:
        raise ValueError("max_lines must be between 1 and 3")

    closed = sorted((_normalize(candle) for candle in candles if _is_closed(candle)), key=lambda item: item.time)
    if len(closed) < 14 + left_candles + right_candles:
        return TrendLineAnalysis([], None, touch_tolerance_atr, break_buffer_atr, minimum_anchor_distance, len(closed), ["Not enough closed candles to confirm an ATR-normalised trend line."])

    atr_values = atr(closed, period=14)
    fallback_atr = max(mean(candle.high - candle.low for candle in closed[-14:]), 1e-12)
    structure = analyze_market_structure(
        candles,
        left_candles=left_candles,
        right_candles=right_candles,
        recent_limit=1000,
    )
    bullish = [point for point in structure.recent_structure_points if point.classification == "HL"][-8:]
    bearish = [point for point in structure.recent_structure_points if point.classification == "LH"][-8:]
    zones = horizontal_zones or []

    all_lines: dict[TrendDirection, list[TrendLine]] = {"bullish": [], "bearish": []}
    for direction, anchors in (("bullish", bullish), ("bearish", bearish)):
        candidates = _candidates(anchors, direction, minimum_anchor_distance, closed, atr_values, violation_buffer_atr)
        for candidate in candidates:
            all_lines[direction].append(
                _evaluate(candidate, anchors, closed, atr_values, fallback_atr, right_candles, touch_tolerance_atr, break_buffer_atr, zones)
            )
        all_lines[direction].sort(key=_rank, reverse=True)

    selected: list[TrendLine] = []
    for direction in ("bullish", "bearish"):
        if all_lines[direction]:
            selected.append(replace(all_lines[direction][0], role="primary"))

    remaining = [line for direction in ("bullish", "bearish") for line in all_lines[direction][1:]]
    remaining.sort(key=_rank, reverse=True)
    if len(selected) < max_lines and remaining:
        selected.append(replace(remaining[0], role="secondary"))
    selected = sorted(selected[:max_lines], key=lambda line: (line.role != "primary", line.direction))

    latest_atr = atr_values[-1] or fallback_atr
    return TrendLineAnalysis(
        lines=selected,
        atr_14=round(latest_atr, 8),
        touch_tolerance_atr=touch_tolerance_atr,
        break_buffer_atr=break_buffer_atr,
        minimum_anchor_distance=minimum_anchor_distance,
        closed_candle_count=len(closed),
        reasons=[
            "Bullish lines use confirmed higher lows; bearish lines use confirmed lower highs.",
            "A line requires two anchors and gains confidence from a third or later ATR-normalised touch.",
            "Breaks, bounces, and retests are evaluated from closed candles only; intrabar wicks cannot break a line.",
        ],
    )


def _candidates(
    anchors: list[StructurePoint],
    direction: TrendDirection,
    minimum_distance: int,
    candles: list[_Candle],
    atr_values: list[float | None],
    violation_buffer_atr: float,
) -> list[_Candidate]:
    result: list[_Candidate] = []
    for first_index, first in enumerate(anchors):
        if atr_values[first.index] is None:
            continue
        for second in anchors[first_index + 1 :]:
            distance = second.index - first.index
            if distance < minimum_distance or atr_values[second.index] is None:
                continue
            slope = (second.price - first.price) / distance
            if (direction == "bullish" and slope <= 0) or (direction == "bearish" and slope >= 0):
                continue
            candidate = _Candidate(first, second, direction, slope)
            if not _major_violation(candidate, candles, atr_values, violation_buffer_atr):
                result.append(candidate)
    return result


def _major_violation(candidate: _Candidate, candles: list[_Candle], atr_values: list[float | None], buffer_atr: float) -> bool:
    for index in range(candidate.first.index + 1, candidate.second.index):
        line_price = _price(candidate, index)
        buffer = (atr_values[index] or 0.0) * buffer_atr
        if candidate.direction == "bullish" and candles[index].close < line_price - buffer:
            return True
        if candidate.direction == "bearish" and candles[index].close > line_price + buffer:
            return True
    return False


def _evaluate(
    candidate: _Candidate,
    confirmed_anchors: list[StructurePoint],
    candles: list[_Candle],
    atr_values: list[float | None],
    fallback_atr: float,
    right_candles: int,
    touch_tolerance_atr: float,
    break_buffer_atr: float,
    zones: list[PriceZone],
) -> TrendLine:
    start_evaluation = candidate.second.index + right_candles + 1
    broken_index: int | None = None
    bounce_index: int | None = None

    for index in range(start_evaluation, len(candles)):
        candle = candles[index]
        candle_atr = atr_values[index] or fallback_atr
        line_price = _price(candidate, index)
        break_buffer = candle_atr * break_buffer_atr
        if candidate.direction == "bullish" and candle.close < line_price - break_buffer:
            broken_index = index
            break
        if candidate.direction == "bearish" and candle.close > line_price + break_buffer:
            broken_index = index
            break
        tolerance = candle_atr * touch_tolerance_atr
        if _touches(candidate.direction, candle, line_price, tolerance) and _holds(candidate.direction, candle.close, line_price):
            bounce_index = index

    retest_index: int | None = None
    if broken_index is not None:
        for index in range(broken_index + 1, len(candles)):
            candle = candles[index]
            tolerance = (atr_values[index] or fallback_atr) * touch_tolerance_atr
            line_price = _price(candidate, index)
            if _retest_touches(candidate.direction, candle, line_price, tolerance) and not _holds(candidate.direction, candle.close, line_price):
                retest_index = index
                break

    end_index = len(candles) - 1
    last_valid_index = broken_index if broken_index is not None else end_index
    touch_indices = {
        anchor.index
        for anchor in confirmed_anchors
        if candidate.first.index <= anchor.index <= last_valid_index
        and abs(anchor.price - _price(candidate, anchor.index)) <= (atr_values[anchor.index] or fallback_atr) * touch_tolerance_atr
    }
    touch_indices.update((candidate.first.index, candidate.second.index))
    end_price = _price(candidate, end_index)
    confluence_tolerance = (atr_values[end_index] or fallback_atr) * touch_tolerance_atr
    confluence = any(
        zone.lower_price - confluence_tolerance <= price <= zone.upper_price + confluence_tolerance
        for zone in zones
        for price in (candidate.first.price, candidate.second.price, end_price)
    )
    latest_touch = max(touch_indices)
    recency = 1 - min(1.0, (end_index - latest_touch) / max(1, len(candles) - 1))
    span = min(1.0, (candidate.second.index - candidate.first.index) / max(1, len(candles) // 3))
    confidence = round(min(100, min(45, len(touch_indices) * 15) + recency * 25 + span * 20 + (10 if confluence else 0)))
    return TrendLine(
        start_time=candidate.first.time,
        start_price=round(candidate.first.price, 8),
        end_time=candles[end_index].time,
        end_price=round(end_price, 8),
        direction=candidate.direction,
        role="primary",
        touch_count=len(touch_indices),
        confidence_score=confidence,
        status="broken" if broken_index is not None else "active",
        broken_at=candles[broken_index].time if broken_index is not None else None,
        bounce_detected=bounce_index is not None,
        bounce_at=candles[bounce_index].time if bounce_index is not None else None,
        break_retested=retest_index is not None,
        retested_at=candles[retest_index].time if retest_index is not None else None,
        failed_retest=retest_index is not None,
        horizontal_zone_confluence=confluence,
        first_anchor_confirmed_at=candidate.first.confirmed_at,
        last_anchor_confirmed_at=candidate.second.confirmed_at,
    )


def _price(candidate: _Candidate, index: int) -> float:
    return candidate.first.price + candidate.slope * (index - candidate.first.index)


def _touches(direction: TrendDirection, candle: _Candle, price: float, tolerance: float) -> bool:
    value = candle.low if direction == "bullish" else candle.high
    return abs(value - price) <= tolerance


def _retest_touches(direction: TrendDirection, candle: _Candle, price: float, tolerance: float) -> bool:
    # After a break the line reverses role: former bullish support is approached
    # from below with the high, while former bearish resistance is approached
    # from above with the low.
    value = candle.high if direction == "bullish" else candle.low
    return abs(value - price) <= tolerance


def _holds(direction: TrendDirection, close: float, price: float) -> bool:
    return close >= price if direction == "bullish" else close <= price


def _rank(line: TrendLine) -> tuple[int, int, int, datetime]:
    return (line.confidence_score, line.touch_count, line.status == "active", line.last_anchor_confirmed_at)


def _normalize(candle: Any) -> _Candle:
    return _Candle(
        time=_read(candle, "opened_at", "time"),
        open=float(_read(candle, "open")),
        high=float(_read(candle, "high")),
        low=float(_read(candle, "low")),
        close=float(_read(candle, "close")),
    )


def _read(candle: Any, *names: str) -> Any:
    for name in names:
        if isinstance(candle, dict) and name in candle:
            return candle[name]
        if hasattr(candle, name):
            return getattr(candle, name)
    raise ValueError(f"Candle is missing required field: {' or '.join(names)}")


def _is_closed(candle: Any) -> bool:
    for name in ("is_closed", "isClosed"):
        if isinstance(candle, dict) and name in candle:
            return bool(candle[name])
        if hasattr(candle, name):
            return bool(getattr(candle, name))
    return True

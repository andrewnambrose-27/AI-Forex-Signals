from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


StructureLabel = Literal["HH", "HL", "LH", "LL"]
StructureDirection = Literal["bullish", "bearish", "ranging", "insufficient_data"]
SwingKind = Literal["high", "low"]


@dataclass(frozen=True)
class SwingPoint:
    index: int
    time: datetime
    confirmed_at: datetime
    price: float
    kind: SwingKind


@dataclass(frozen=True)
class StructurePoint(SwingPoint):
    classification: StructureLabel


@dataclass(frozen=True)
class MarketStructureResult:
    latest_confirmed_swing_high: SwingPoint | None
    latest_confirmed_swing_low: SwingPoint | None
    recent_structure_points: list[StructurePoint]
    direction: StructureDirection
    confidence_score: int
    reasons: list[str]
    left_candles: int
    right_candles: int
    closed_candle_count: int


def analyze_market_structure(
    candles: list[Any],
    *,
    left_candles: int = 3,
    right_candles: int = 3,
    recent_limit: int = 20,
) -> MarketStructureResult:
    """Analyze confirmed pivots using closed candles available at evaluation time.

    A pivot at index ``i`` is emitted only when candle ``i + right_candles`` is
    present and closed. Strict comparisons make equal-price plateaus deterministic
    and prevent multiple candles from claiming the same pivot.
    """
    if left_candles < 1 or right_candles < 1:
        raise ValueError("left_candles and right_candles must both be at least 1")
    if recent_limit < 1:
        raise ValueError("recent_limit must be at least 1")

    closed = sorted((_normalize(candle) for candle in candles if _is_closed(candle)), key=lambda candle: candle.time)
    pivots = detect_confirmed_pivots(candles, left_candles=left_candles, right_candles=right_candles)
    swing_highs = [point for point in pivots if point.kind == "high"]
    swing_lows = [point for point in pivots if point.kind == "low"]
    structure_points: list[StructurePoint] = []

    for points, higher_label, lower_label in ((swing_highs, "HH", "LH"), (swing_lows, "HL", "LL")):
        for previous, point in zip(points, points[1:]):
            structure_points.append(
                StructurePoint(**point.__dict__, classification=higher_label if point.price > previous.price else lower_label)
            )

    structure_points.sort(key=lambda point: (point.confirmed_at, point.time, point.kind))
    direction, confidence, reasons = _classify_state(swing_highs, swing_lows, structure_points)
    return MarketStructureResult(
        latest_confirmed_swing_high=swing_highs[-1] if swing_highs else None,
        latest_confirmed_swing_low=swing_lows[-1] if swing_lows else None,
        recent_structure_points=structure_points[-recent_limit:],
        direction=direction,
        confidence_score=confidence,
        reasons=reasons,
        left_candles=left_candles,
        right_candles=right_candles,
        closed_candle_count=len(closed),
    )


def detect_confirmed_pivots(
    candles: list[Any],
    *,
    left_candles: int = 3,
    right_candles: int = 3,
) -> list[SwingPoint]:
    if left_candles < 1 or right_candles < 1:
        raise ValueError("left_candles and right_candles must both be at least 1")

    closed = sorted((_normalize(candle) for candle in candles if _is_closed(candle)), key=lambda candle: candle.time)
    pivots: list[SwingPoint] = []
    for index in range(left_candles, len(closed) - right_candles):
        candle = closed[index]
        neighbours = (*closed[index - left_candles : index], *closed[index + 1 : index + right_candles + 1])
        confirmed_at = closed[index + right_candles].time
        if all(candle.high > neighbour.high for neighbour in neighbours):
            pivots.append(SwingPoint(index=index, time=candle.time, confirmed_at=confirmed_at, price=candle.high, kind="high"))
        if all(candle.low < neighbour.low for neighbour in neighbours):
            pivots.append(SwingPoint(index=index, time=candle.time, confirmed_at=confirmed_at, price=candle.low, kind="low"))
    return sorted(pivots, key=lambda point: (point.confirmed_at, point.time, point.kind))


@dataclass(frozen=True)
class _Candle:
    time: datetime
    high: float
    low: float


def _normalize(candle: Any) -> _Candle:
    return _Candle(
        time=_read(candle, "opened_at", "time"),
        high=float(_read(candle, "high")),
        low=float(_read(candle, "low")),
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
    # Stored and IG REST candles have already passed the closed-candle filter.
    return True


def _classify_state(
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    points: list[StructurePoint],
) -> tuple[StructureDirection, int, list[str]]:
    if len(highs) < 2 or len(lows) < 2:
        return (
            "insufficient_data",
            0,
            [
                f"Need two confirmed swing highs and two confirmed swing lows; found {len(highs)} high(s) and {len(lows)} low(s).",
                "Only closed candles can complete the right-side confirmation window.",
            ],
        )

    latest_high = "HH" if highs[-1].price > highs[-2].price else "LH"
    latest_low = "HL" if lows[-1].price > lows[-2].price else "LL"
    if latest_high == "HH" and latest_low == "HL":
        direction: StructureDirection = "bullish"
        expected = {"HH", "HL"}
        reason = "The latest confirmed high is HH and the latest confirmed low is HL."
    elif latest_high == "LH" and latest_low == "LL":
        direction = "bearish"
        expected = {"LH", "LL"}
        reason = "The latest confirmed high is LH and the latest confirmed low is LL."
    else:
        direction = "ranging"
        expected = set()
        reason = f"The latest confirmed structure is mixed ({latest_high} high, {latest_low} low)."

    recent = points[-6:]
    if direction == "ranging":
        confidence = 55 if latest_high in {"HH", "LH"} and latest_low in {"HL", "LL"} else 40
        reasons = [reason, "Mixed high/low progression does not establish a directional sequence."]
    else:
        alignment = sum(point.classification in expected for point in recent) / len(recent) if recent else 0
        confidence = round(65 + (35 * alignment))
        reasons = [reason, f"{sum(point.classification in expected for point in recent)} of the last {len(recent)} classified pivots support this direction."]
    return direction, confidence, reasons

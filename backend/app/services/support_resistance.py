from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from statistics import mean
from typing import Any, Literal

from app.services.market_structure import SwingPoint, detect_confirmed_pivots
from app.services.technical_indicators import atr


ZoneType = Literal["support", "resistance", "mixed"]
BreakDirection = Literal["above", "below"]


@dataclass(frozen=True)
class PriceZone:
    lower_price: float
    upper_price: float
    centre_price: float
    type: ZoneType
    confirmed_touches: int
    first_touch_time: datetime
    most_recent_touch_time: datetime
    strength_score: int
    broken: bool
    retested: bool
    higher_timeframe_confluence: bool
    break_direction: BreakDirection | None = None
    broken_at: datetime | None = None
    retested_at: datetime | None = None
    rejection_strength: float = 0.0


@dataclass(frozen=True)
class ZoneAnalysis:
    zones: list[PriceZone]
    atr_14: float | None
    clustering_distance_atr: float
    break_buffer_atr: float
    closed_candle_count: int
    reasons: list[str]


@dataclass(frozen=True)
class _Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class _Cluster:
    touches: list[SwingPoint]
    prices: list[float]
    atr_values: list[float]

    @property
    def centre(self) -> float:
        return mean(self.prices)

    @property
    def threshold(self) -> float:
        return mean(self.atr_values)


def detect_support_resistance_zones(
    candles: list[Any],
    *,
    left_candles: int = 3,
    right_candles: int = 3,
    clustering_distance_atr: float = 0.25,
    break_buffer_atr: float = 0.1,
    min_touches: int = 2,
    higher_timeframe_zones: list[PriceZone] | None = None,
    max_zones: int | None = None,
) -> ZoneAnalysis:
    if clustering_distance_atr <= 0:
        raise ValueError("clustering_distance_atr must be greater than zero")
    if break_buffer_atr < 0:
        raise ValueError("break_buffer_atr cannot be negative")
    if min_touches < 1:
        raise ValueError("min_touches must be at least 1")

    closed = sorted((_normalize(candle) for candle in candles if _is_closed(candle)), key=lambda candle: candle.time)
    if len(closed) < left_candles + right_candles + 1:
        return ZoneAnalysis([], None, clustering_distance_atr, break_buffer_atr, len(closed), ["Not enough closed candles to confirm a price zone."])

    atr_values = atr(closed, period=14)
    fallback_atr = _fallback_atr(closed)
    pivots = detect_confirmed_pivots(candles, left_candles=left_candles, right_candles=right_candles)
    clusters: list[_Cluster] = []
    for pivot in pivots:
        pivot_atr = atr_values[pivot.index]
        if pivot_atr is None:
            continue
        distance = max(pivot_atr * clustering_distance_atr, 1e-12)
        candidates = [cluster for cluster in clusters if abs(cluster.centre - pivot.price) <= max(cluster.threshold, distance)]
        if candidates:
            cluster = min(candidates, key=lambda item: abs(item.centre - pivot.price))
            cluster.touches.append(pivot)
            cluster.prices.append(pivot.price)
            cluster.atr_values.append(distance)
        else:
            clusters.append(_Cluster([pivot], [pivot.price], [distance]))

    clusters = _merge_overlapping_clusters(clusters)
    zones = [
        _build_zone(cluster, closed, atr_values, fallback_atr, break_buffer_atr, right_candles, higher_timeframe_zones or [])
        for cluster in clusters
        if len(cluster.touches) >= min_touches
    ]
    latest_price = closed[-1].close
    latest_atr = atr_values[-1] or fallback_atr
    zones.sort(key=lambda zone: (_relevance(zone, latest_price, latest_atr), zone.strength_score), reverse=True)
    if max_zones is not None:
        zones = zones[:max_zones]
    return ZoneAnalysis(
        zones=zones,
        atr_14=round(latest_atr, 8),
        clustering_distance_atr=clustering_distance_atr,
        break_buffer_atr=break_buffer_atr,
        closed_candle_count=len(closed),
        reasons=[
            f"Zones cluster confirmed pivots within {clustering_distance_atr:.2f} x ATR(14).",
            "Pivots before ATR(14) warm-up completes are not used to form zones.",
            "Strength uses confirmed touches, recency, rejection strength, and higher-timeframe confluence; volume is excluded.",
        ],
    )


def _build_zone(
    cluster: _Cluster,
    candles: list[_Candle],
    atr_values: list[float | None],
    fallback_atr: float,
    break_buffer_atr: float,
    right_candles: int,
    higher_zones: list[PriceZone],
) -> PriceZone:
    kinds = {touch.kind for touch in cluster.touches}
    zone_type: ZoneType = "mixed" if len(kinds) > 1 else "resistance" if "high" in kinds else "support"
    padding = max(mean(cluster.atr_values) * 0.2, 1e-12)
    lower = min(cluster.prices) - padding
    upper = max(cluster.prices) + padding
    centre = mean(cluster.prices)
    first_touch = min(touch.time for touch in cluster.touches)
    recent_touch = max(touch.time for touch in cluster.touches)
    ordered_touches = sorted(cluster.touches, key=lambda touch: touch.confirmed_at)
    latest_touch = ordered_touches[-1]
    formation_touch = ordered_touches[min(1, len(ordered_touches) - 1)]
    rejection = mean(_rejection_strength(touch, candles, atr_values[touch.index] or fallback_atr) for touch in cluster.touches)
    higher_confluence = any(_overlaps(lower, upper, zone.lower_price, zone.upper_price, fallback_atr * 0.25) for zone in higher_zones)
    recency = 1 - min(1.0, max(0, len(candles) - 1 - latest_touch.index) / max(1, len(candles) - 1))
    strength = round(min(100, min(40, len(cluster.touches) * 10) + (recency * 20) + (min(1.0, rejection) * 25) + (15 if higher_confluence else 0)))
    zone = PriceZone(
        lower_price=round(lower, 8),
        upper_price=round(upper, 8),
        centre_price=round(centre, 8),
        type=zone_type,
        confirmed_touches=len(cluster.touches),
        first_touch_time=first_touch,
        most_recent_touch_time=recent_touch,
        strength_score=strength,
        broken=False,
        retested=False,
        higher_timeframe_confluence=higher_confluence,
        rejection_strength=round(rejection, 3),
    )
    return _mark_break_and_retest(zone, candles, atr_values, fallback_atr, formation_touch.index + right_candles + 1, break_buffer_atr)


def _mark_break_and_retest(
    zone: PriceZone,
    candles: list[_Candle],
    atr_values: list[float | None],
    fallback_atr: float,
    start_index: int,
    break_buffer_atr: float,
) -> PriceZone:
    broken: PriceZone | None = None
    broken_index: int | None = None
    for index in range(start_index, len(candles)):
        candle_atr = atr_values[index] or fallback_atr
        buffer = candle_atr * break_buffer_atr
        if zone.type in {"resistance", "mixed"} and candles[index].close > zone.upper_price + buffer:
            broken = replace(zone, broken=True, break_direction="above", broken_at=candles[index].time)
            broken_index = index
            break
        if zone.type in {"support", "mixed"} and candles[index].close < zone.lower_price - buffer:
            broken = replace(zone, broken=True, break_direction="below", broken_at=candles[index].time)
            broken_index = index
            break
    if broken is None or broken_index is None:
        return zone

    for index in range(broken_index + 1, len(candles)):
        candle = candles[index]
        tolerance = (atr_values[index] or fallback_atr) * 0.15
        if broken.break_direction == "above" and candle.low <= broken.upper_price + tolerance and candle.high >= broken.lower_price and candle.close >= broken.upper_price:
            return replace(broken, retested=True, retested_at=candle.time)
        if broken.break_direction == "below" and candle.high >= broken.lower_price - tolerance and candle.low <= broken.upper_price and candle.close <= broken.lower_price:
            return replace(broken, retested=True, retested_at=candle.time)
    return broken


def _merge_overlapping_clusters(clusters: list[_Cluster]) -> list[_Cluster]:
    merged: list[_Cluster] = []
    for cluster in sorted(clusters, key=lambda item: item.centre):
        if merged and abs(merged[-1].centre - cluster.centre) <= max(merged[-1].threshold, cluster.threshold):
            merged[-1].touches.extend(cluster.touches)
            merged[-1].prices.extend(cluster.prices)
            merged[-1].atr_values.extend(cluster.atr_values)
        else:
            merged.append(cluster)
    return merged


def _rejection_strength(touch: SwingPoint, candles: list[_Candle], atr_value: float) -> float:
    candle = candles[touch.index]
    wick = candle.high - max(candle.open, candle.close) if touch.kind == "high" else min(candle.open, candle.close) - candle.low
    return max(0.0, wick / max(atr_value, 1e-12))


def _fallback_atr(candles: list[_Candle]) -> float:
    ranges = [candle.high - candle.low for candle in candles[-14:]]
    return max(mean(ranges), 1e-12)


def _relevance(zone: PriceZone, price: float, atr_value: float) -> float:
    distance = abs(zone.centre_price - price) / max(atr_value, 1e-12)
    state_bonus = 20 if not zone.broken else 10 if zone.retested else 0
    return zone.strength_score + state_bonus - min(30, distance * 3)


def _overlaps(lower_a: float, upper_a: float, lower_b: float, upper_b: float, tolerance: float) -> bool:
    return lower_a <= upper_b + tolerance and lower_b <= upper_a + tolerance


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

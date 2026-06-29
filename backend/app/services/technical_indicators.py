from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean, pstdev
from typing import Any, Iterable, Sequence


Number = int | float
Series = list[float | None]


@dataclass(frozen=True)
class OHLC:
    open: float
    high: float
    low: float
    close: float


def normalize_candles(candles: Iterable[Any]) -> list[OHLC]:
    normalized: list[OHLC] = []
    for candle in candles:
        normalized.append(
            OHLC(
                open=_read_float(candle, "open"),
                high=_read_float(candle, "high"),
                low=_read_float(candle, "low"),
                close=_read_float(candle, "close"),
            )
        )
    return normalized


def ema(values: Sequence[Number], period: int) -> Series:
    _require_period(period)
    if not values:
        return []

    floats = [_as_float(value) for value in values]
    result: Series = [None] * len(floats)
    if len(floats) < period:
        return result

    multiplier = 2 / (period + 1)
    previous_ema = mean(floats[:period])
    result[period - 1] = previous_ema

    for index in range(period, len(floats)):
        previous_ema = (floats[index] - previous_ema) * multiplier + previous_ema
        result[index] = previous_ema

    return result


def ema_set(candles: Iterable[Any]) -> dict[str, Series]:
    closes = _closes(candles)
    return {
        "ema_20": ema(closes, 20),
        "ema_50": ema(closes, 50),
        "ema_200": ema(closes, 200),
    }


def rsi(candles: Iterable[Any], period: int = 14) -> Series:
    _require_period(period)
    closes = _closes(candles)
    result: Series = [None] * len(closes)
    if len(closes) <= period:
        return result

    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    average_gain = mean(gains)
    average_loss = mean(losses)
    result[period] = _rsi_value(average_gain, average_loss)

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0)
        loss = abs(min(change, 0))
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period
        result[index] = _rsi_value(average_gain, average_loss)

    return result


def macd(
    candles: Iterable[Any],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, Series]:
    closes = _closes(candles)
    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)
    macd_line: Series = [
        fast_value - slow_value if fast_value is not None and slow_value is not None else None
        for fast_value, slow_value in zip(fast, slow)
    ]
    signal_line = _ema_nullable(macd_line, signal_period)
    histogram: Series = [
        macd_value - signal_value if macd_value is not None and signal_value is not None else None
        for macd_value, signal_value in zip(macd_line, signal_line)
    ]
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    }


def atr(candles: Iterable[Any], period: int = 14) -> Series:
    _require_period(period)
    data = normalize_candles(candles)
    true_ranges = _true_ranges(data)
    result: Series = [None] * len(data)
    if len(true_ranges) < period:
        return result

    previous_atr = mean(true_ranges[:period])
    result[period - 1] = previous_atr
    for index in range(period, len(true_ranges)):
        previous_atr = ((previous_atr * (period - 1)) + true_ranges[index]) / period
        result[index] = previous_atr

    return result


def adx(candles: Iterable[Any], period: int = 14) -> dict[str, Series]:
    _require_period(period)
    data = normalize_candles(candles)
    size = len(data)
    plus_dm = [0.0] * size
    minus_dm = [0.0] * size
    true_ranges = _true_ranges(data)

    for index in range(1, size):
        up_move = data[index].high - data[index - 1].high
        down_move = data[index - 1].low - data[index].low
        plus_dm[index] = up_move if up_move > down_move and up_move > 0 else 0
        minus_dm[index] = down_move if down_move > up_move and down_move > 0 else 0

    plus_di: Series = [None] * size
    minus_di: Series = [None] * size
    dx: Series = [None] * size
    adx_values: Series = [None] * size
    if size <= period:
        return {"adx": adx_values, "plus_di": plus_di, "minus_di": minus_di}

    smoothed_tr = sum(true_ranges[1 : period + 1])
    smoothed_plus_dm = sum(plus_dm[1 : period + 1])
    smoothed_minus_dm = sum(minus_dm[1 : period + 1])

    for index in range(period, size):
        if index > period:
            smoothed_tr = smoothed_tr - (smoothed_tr / period) + true_ranges[index]
            smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / period) + plus_dm[index]
            smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / period) + minus_dm[index]

        if smoothed_tr == 0:
            plus_di[index] = 0
            minus_di[index] = 0
            dx[index] = 0
            continue

        plus_di[index] = 100 * smoothed_plus_dm / smoothed_tr
        minus_di[index] = 100 * smoothed_minus_dm / smoothed_tr
        total = plus_di[index] + minus_di[index]
        dx[index] = 0 if total == 0 else 100 * abs(plus_di[index] - minus_di[index]) / total

    first_dx_window = [value for value in dx[period : period * 2] if value is not None]
    if len(first_dx_window) == period:
        adx_index = (period * 2) - 1
        previous_adx = mean(first_dx_window)
        adx_values[adx_index] = previous_adx
        for index in range(adx_index + 1, size):
            if dx[index] is None:
                continue
            previous_adx = ((previous_adx * (period - 1)) + dx[index]) / period
            adx_values[index] = previous_adx

    return {"adx": adx_values, "plus_di": plus_di, "minus_di": minus_di}


def bollinger_bands(candles: Iterable[Any], period: int = 20, standard_deviations: float = 2) -> dict[str, Series]:
    _require_period(period)
    closes = _closes(candles)
    middle: Series = [None] * len(closes)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)

    for index in range(period - 1, len(closes)):
        window = closes[index - period + 1 : index + 1]
        window_mean = mean(window)
        deviation = pstdev(window)
        middle[index] = window_mean
        upper[index] = window_mean + standard_deviations * deviation
        lower[index] = window_mean - standard_deviations * deviation

    return {"middle": middle, "upper": upper, "lower": lower}


def recent_swing_highs_lows(candles: Iterable[Any], lookback: int = 3) -> dict[str, list[dict[str, float | int]]]:
    _require_period(lookback)
    data = normalize_candles(candles)
    swing_highs: list[dict[str, float | int]] = []
    swing_lows: list[dict[str, float | int]] = []

    for index in range(lookback, len(data) - lookback):
        window = data[index - lookback : index + lookback + 1]
        high = data[index].high
        low = data[index].low
        if high == max(candle.high for candle in window):
            swing_highs.append({"index": index, "price": high})
        if low == min(candle.low for candle in window):
            swing_lows.append({"index": index, "price": low})

    return {"swing_highs": swing_highs, "swing_lows": swing_lows}


def support_resistance_zones(
    candles: Iterable[Any],
    lookback: int = 3,
    tolerance_percent: float = 0.15,
    min_touches: int = 2,
) -> dict[str, list[dict[str, float | int]]]:
    swings = recent_swing_highs_lows(candles, lookback=lookback)
    resistance = _cluster_pivots(swings["swing_highs"], tolerance_percent, min_touches)
    support = _cluster_pivots(swings["swing_lows"], tolerance_percent, min_touches)
    return {"support": support, "resistance": resistance}


def calculate_all_indicators(candles: Iterable[Any]) -> dict[str, Any]:
    data = list(candles)
    return {
        **ema_set(data),
        "rsi_14": rsi(data, 14),
        "macd": macd(data),
        "adx": adx(data),
        "atr": atr(data),
        "bollinger_bands": bollinger_bands(data),
        "swings": recent_swing_highs_lows(data),
        "support_resistance": support_resistance_zones(data),
    }


def _cluster_pivots(
    pivots: list[dict[str, float | int]],
    tolerance_percent: float,
    min_touches: int,
) -> list[dict[str, float | int]]:
    zones: list[dict[str, Any]] = []
    for pivot in pivots:
        price = float(pivot["price"])
        matched_zone = None
        for zone in zones:
            tolerance = zone["price"] * (tolerance_percent / 100)
            if abs(price - zone["price"]) <= tolerance:
                matched_zone = zone
                break

        if matched_zone is None:
            zones.append({"price": price, "touches": 1, "first_index": pivot["index"], "last_index": pivot["index"]})
            continue

        touches = matched_zone["touches"] + 1
        matched_zone["price"] = ((matched_zone["price"] * matched_zone["touches"]) + price) / touches
        matched_zone["touches"] = touches
        matched_zone["last_index"] = pivot["index"]

    return [
        {
            "price": zone["price"],
            "touches": zone["touches"],
            "first_index": zone["first_index"],
            "last_index": zone["last_index"],
        }
        for zone in zones
        if zone["touches"] >= min_touches
    ]


def _ema_nullable(values: Sequence[float | None], period: int) -> Series:
    result: Series = [None] * len(values)
    valid_values: list[float] = []
    valid_indexes: list[int] = []

    for index, value in enumerate(values):
        if value is None:
            continue
        valid_values.append(value)
        valid_indexes.append(index)

    valid_ema = ema(valid_values, period)
    for source_index, value in zip(valid_indexes, valid_ema):
        result[source_index] = value

    return result


def _true_ranges(candles: Sequence[OHLC]) -> list[float]:
    true_ranges: list[float] = []
    for index, candle in enumerate(candles):
        if index == 0:
            true_ranges.append(candle.high - candle.low)
            continue
        previous_close = candles[index - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    return true_ranges


def _closes(candles: Iterable[Any]) -> list[float]:
    return [candle.close for candle in normalize_candles(candles)]


def _read_float(candle: Any, key: str) -> float:
    if isinstance(candle, dict):
        return _as_float(candle[key])
    return _as_float(getattr(candle, key))


def _as_float(value: Any) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError("Indicator inputs must be finite numbers")
    return number


def _require_period(period: int) -> None:
    if period <= 0:
        raise ValueError("Period must be greater than zero")


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))

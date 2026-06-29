from app.services.technical_indicators import (
    adx,
    atr,
    bollinger_bands,
    calculate_all_indicators,
    ema,
    ema_set,
    macd,
    recent_swing_highs_lows,
    rsi,
    support_resistance_zones,
)


def sample_candles(count: int = 260):
    candles = []
    close = 1.1000
    for index in range(count):
        wave = ((index % 18) - 9) * 0.00035
        trend = index * 0.00006
        open_price = close
        close = 1.1000 + trend + wave
        high = max(open_price, close) + 0.0012 + ((index % 4) * 0.00008)
        low = min(open_price, close) - 0.0011 - ((index % 5) * 0.00007)
        candles.append(
            {
                "open": round(open_price, 5),
                "high": round(high, 5),
                "low": round(low, 5),
                "close": round(close, 5),
            }
        )
    return candles


def test_ema_returns_expected_shape_and_seed_value():
    values = [float(value) for value in range(1, 31)]
    result = ema(values, 10)

    assert len(result) == len(values)
    assert result[:9] == [None] * 9
    assert result[9] == 5.5
    assert result[-1] is not None
    assert result[-1] > result[9]


def test_core_indicators_return_series_matching_candle_count():
    candles = sample_candles()
    count = len(candles)

    emas = ema_set(candles)
    macd_values = macd(candles)
    adx_values = adx(candles)
    bands = bollinger_bands(candles)

    assert len(emas["ema_20"]) == count
    assert len(emas["ema_50"]) == count
    assert len(emas["ema_200"]) == count
    assert len(rsi(candles)) == count
    assert len(macd_values["macd"]) == count
    assert len(macd_values["signal"]) == count
    assert len(adx_values["adx"]) == count
    assert len(atr(candles)) == count
    assert len(bands["upper"]) == count
    assert emas["ema_200"][-1] is not None
    assert macd_values["histogram"][-1] is not None
    assert adx_values["plus_di"][-1] is not None
    assert bands["upper"][-1] > bands["middle"][-1] > bands["lower"][-1]


def test_swings_and_support_resistance_detect_repeated_pivots():
    candles = [
        {"open": 9, "high": 10, "low": 8, "close": 9},
        {"open": 10, "high": 12, "low": 9, "close": 11},
        {"open": 11, "high": 15, "low": 10, "close": 14},
        {"open": 14, "high": 12, "low": 8, "close": 9},
        {"open": 9, "high": 10, "low": 6, "close": 7},
        {"open": 7, "high": 12, "low": 8, "close": 11},
        {"open": 11, "high": 15.02, "low": 10, "close": 14},
        {"open": 14, "high": 12, "low": 8, "close": 9},
        {"open": 9, "high": 10, "low": 6.01, "close": 7},
        {"open": 7, "high": 11, "low": 8, "close": 10},
    ]

    swings = recent_swing_highs_lows(candles, lookback=1)
    zones = support_resistance_zones(candles, lookback=1, tolerance_percent=0.2, min_touches=2)

    assert len(swings["swing_highs"]) >= 2
    assert len(swings["swing_lows"]) >= 2
    assert zones["resistance"][0]["touches"] >= 2
    assert zones["support"][0]["touches"] >= 2


def test_calculate_all_indicators_combines_outputs():
    result = calculate_all_indicators(sample_candles())

    assert "ema_20" in result
    assert "rsi_14" in result
    assert "macd" in result
    assert "adx" in result
    assert "atr" in result
    assert "bollinger_bands" in result
    assert "swings" in result
    assert "support_resistance" in result

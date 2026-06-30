from types import SimpleNamespace

from app.services.signal_engine import evaluate_strategies


def rising_candles(count: int = 260):
    candles = []
    price = 1.1000
    for index in range(count):
        close = price + 0.00012
        candles.append(
            SimpleNamespace(
                open=round(price, 5),
                high=round(close + 0.0004, 5),
                low=round(price - 0.0003, 5),
                close=round(close, 5),
            )
        )
        price = close
    return candles


def test_strategy_engine_returns_trend_buy_signal_from_closed_candles():
    primary = rising_candles()
    higher = rising_candles()
    primary[-3] = SimpleNamespace(open=1.1290, high=1.1294, low=1.1280, close=1.1282)
    primary[-2] = SimpleNamespace(open=1.1282, high=1.1365, low=1.1280, close=1.1362)
    primary[-1] = SimpleNamespace(open=9.0, high=10.0, low=8.0, close=9.5)

    result = evaluate_strategies(
        epic="CS.D.EURUSD.MINI.IP",
        pair="EURUSD",
        timeframe="1h",
        minimum_score=50,
        candles_by_timeframe={"1h": primary, "4h": higher},
    )

    assert result.direction == "BUY"
    assert result.status == "active"
    assert result.strategy == "trend_continuation"
    assert result.entry_reference_price is not None
    assert "closed_candles_only" in result.filters_passed


def test_strategy_engine_filters_when_history_is_too_short():
    result = evaluate_strategies(
        epic="CS.D.EURUSD.MINI.IP",
        pair="EURUSD",
        timeframe="5m",
        minimum_score=60,
        candles_by_timeframe={"5m": rising_candles(20), "15m": rising_candles(20)},
    )

    assert result.direction == "NONE"
    assert result.status == "filtered"
    assert "not_enough_closed_primary_candles" in result.filters_failed


def test_strategy_engine_drops_incomplete_latest_candle():
    primary = rising_candles()
    higher = rising_candles()
    primary[-3] = SimpleNamespace(open=1.1290, high=1.1294, low=1.1280, close=1.1282)
    primary[-2] = SimpleNamespace(open=1.1282, high=1.1365, low=1.1280, close=1.1362)
    primary[-1] = SimpleNamespace(open=0.5, high=0.6, low=0.4, close=0.45)

    result = evaluate_strategies(
        epic="CS.D.EURUSD.MINI.IP",
        pair="EURUSD",
        timeframe="1h",
        minimum_score=50,
        candles_by_timeframe={"1h": primary, "4h": higher},
    )

    assert result.direction == "BUY"
    assert result.entry_reference_price is not None
    assert float(result.entry_reference_price) > 1.0

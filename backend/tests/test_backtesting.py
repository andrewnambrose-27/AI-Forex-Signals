from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from app.services.backtesting import run_backtest
from app.services.market_structure import analyze_market_structure
from app.services.trend_lines import detect_trend_lines
from app.services.multi_timeframe import closed_candles_available_at


def rising_candles(count: int = 260, start: float = 1.1000):
    candles = []
    price = start
    base_time = datetime(2026, 6, 30, 0, 0, tzinfo=timezone.utc)
    for index in range(count):
        close = price + 0.00012
        candles.append(
            SimpleNamespace(
                opened_at=base_time + timedelta(minutes=5 * index),
                open=round(price, 5),
                high=round(close + 0.0004, 5),
                low=round(price - 0.0003, 5),
                close=round(close, 5),
            )
        )
        price = close
    return candles


def test_backtest_returns_metrics_without_lookahead_entry():
    primary = rising_candles()
    higher = rising_candles()
    primary[118] = SimpleNamespace(opened_at=primary[118].opened_at, open=1.1100, high=1.1104, low=1.1080, close=1.1082)
    primary[119] = SimpleNamespace(opened_at=primary[119].opened_at, open=1.1082, high=1.1165, low=1.1080, close=1.1162)
    primary[120] = SimpleNamespace(opened_at=primary[120].opened_at, open=1.1164, high=1.1195, low=1.1155, close=1.1180)

    result = run_backtest(
        pair="EURUSD",
        timeframe="5m",
        primary_candles=primary,
        higher_candles=higher,
        economic_events=[],
        minimum_score=50,
        spread_points=0,
        slippage_points=0,
    )

    assert result.metrics["number_of_trades"] >= 1
    assert result.trades[0].entry_time > primary[119].opened_at
    assert "win_rate" in result.metrics
    assert "performance_by_session" in result.metrics


def test_backtest_empty_result_has_zero_metrics():
    candles = rising_candles(90)

    result = run_backtest(
        pair="EURUSD",
        timeframe="5m",
        primary_candles=candles,
        higher_candles=candles,
        economic_events=[],
        minimum_score=100,
        spread_points=0.0001,
        slippage_points=0.00002,
    )

    assert result.metrics["number_of_trades"] == 0
    assert result.metrics["win_rate"] == 0


def test_walk_forward_structure_never_receives_future_candles():
    candles = rising_candles(40)
    # Add deterministic alternating swings to otherwise rising test data.
    for index, offset in enumerate((0, 4, 2, -2, 1, 5, 3, -1, 2, 6, 4, 0, 3, 7, 5, 1)):
        candle = candles[index]
        midpoint = 1.10 + offset * 0.001
        candles[index] = SimpleNamespace(
            opened_at=candle.opened_at,
            open=midpoint,
            high=midpoint + 0.0004,
            low=midpoint - 0.0004,
            close=midpoint,
        )

    for end_index in range(5, 16):
        walk_forward = analyze_market_structure(candles[: end_index + 1], left_candles=1, right_candles=2)
        later = analyze_market_structure(candles[: min(len(candles), end_index + 8)], left_candles=1, right_candles=2)
        cutoff = candles[end_index].opened_at
        later_points_available_then = [point for point in later.recent_structure_points if point.confirmed_at <= cutoff]

        assert later_points_available_then == walk_forward.recent_structure_points
        assert all(point.confirmed_at <= cutoff for point in walk_forward.recent_structure_points)


def test_walk_forward_trend_lines_use_only_confirmed_anchors_and_ignore_open_future_bar():
    candles = rising_candles(40, start=1.1)
    for index, low in ((14, 1.090), (18, 1.091), (22, 1.092), (26, 1.093), (30, 1.094), (34, 1.095)):
        candle = candles[index]
        candles[index] = SimpleNamespace(opened_at=candle.opened_at, open=1.1, high=1.105, low=low, close=1.1)
    for index, high in ((16, 1.120), (20, 1.119), (24, 1.118), (28, 1.117), (32, 1.116), (36, 1.115)):
        candle = candles[index]
        candles[index] = SimpleNamespace(opened_at=candle.opened_at, open=1.1, high=high, low=1.095, close=1.1)

    for end_index in range(28, 38):
        prefix = candles[: end_index + 1]
        result = detect_trend_lines(prefix, left_candles=1, right_candles=1, minimum_anchor_distance=5)
        cutoff = candles[end_index].opened_at
        assert all(line.last_anchor_confirmed_at <= cutoff for line in result.lines)

        open_future = SimpleNamespace(
            opened_at=cutoff + timedelta(minutes=5), open=1.1, high=2.0, low=0.1, close=0.1, is_closed=False
        )
        assert detect_trend_lines([*prefix, open_future], left_candles=1, right_candles=1, minimum_anchor_distance=5) == result


def test_backtest_higher_timeframe_window_excludes_candle_until_it_closes():
    opened_at = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    one_hour_candle = SimpleNamespace(opened_at=opened_at, open=1.1, high=1.2, low=1.0, close=1.15)

    assert closed_candles_available_at([one_hour_candle], "1h", opened_at + timedelta(minutes=59, seconds=59)) == []
    assert closed_candles_available_at([one_hour_candle], "1h", opened_at + timedelta(hours=1)) == [one_hour_candle]

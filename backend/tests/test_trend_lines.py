from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.main import app
from app.services.support_resistance import PriceZone
from app.services.trend_lines import detect_trend_lines


def _trend_candles():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    candles = [
        SimpleNamespace(
            opened_at=start + timedelta(minutes=5 * index),
            open=110.0,
            high=115.0,
            low=105.0,
            close=110.0,
            is_closed=True,
        )
        for index in range(35)
    ]
    for index, price in ((14, 100.0), (18, 101.0), (22, 102.0), (26, 103.0), (30, 104.0), (34, 105.0)):
        candles[index].low = price
    for index, price in ((16, 120.0), (20, 119.0), (24, 118.0), (28, 117.0), (32, 116.0)):
        candles[index].high = price
    return candles


def test_returns_bounded_confirmed_bullish_and_bearish_lines():
    result = detect_trend_lines(_trend_candles(), left_candles=1, right_candles=1, minimum_anchor_distance=5)

    assert 1 <= len(result.lines) <= 3
    assert {line.direction for line in result.lines} == {"bullish", "bearish"}
    assert all(line.touch_count >= 2 for line in result.lines)
    assert all(line.last_anchor_confirmed_at <= line.end_time for line in result.lines)
    assert sum(line.role == "primary" for line in result.lines) == 2


def test_open_streaming_candle_cannot_change_or_break_a_line():
    candles = _trend_candles()
    open_preview = SimpleNamespace(
        opened_at=candles[-1].opened_at + timedelta(minutes=5),
        open=110.0,
        high=140.0,
        low=80.0,
        close=80.0,
        is_closed=False,
    )

    assert detect_trend_lines([*candles, open_preview], left_candles=1, right_candles=1) == detect_trend_lines(candles, left_candles=1, right_candles=1)


def test_wick_does_not_break_line_but_buffered_close_does_and_can_retest():
    candles = _trend_candles()
    next_time = candles[-1].opened_at + timedelta(minutes=5)
    wick = SimpleNamespace(opened_at=next_time, open=110.0, high=112.0, low=80.0, close=110.0, is_closed=True)
    wick_result = detect_trend_lines([*candles, wick], left_candles=1, right_candles=1)
    assert any(line.direction == "bullish" and line.status == "active" for line in wick_result.lines)

    broken = SimpleNamespace(opened_at=next_time, open=110.0, high=112.0, low=80.0, close=80.0, is_closed=True)
    retest = SimpleNamespace(opened_at=next_time + timedelta(minutes=5), open=90.0, high=107.0, low=89.0, close=90.0, is_closed=True)
    broken_result = detect_trend_lines([*candles, broken, retest], left_candles=1, right_candles=1)
    bullish = next(line for line in broken_result.lines if line.direction == "bullish")
    assert bullish.status == "broken"
    assert bullish.broken_at == next_time
    assert bullish.break_retested is True
    assert bullish.failed_retest is True


def test_horizontal_zone_confluence_increases_line_evidence():
    candles = _trend_candles()
    zone = PriceZone(
        lower_price=100.5,
        upper_price=105.5,
        centre_price=103.0,
        type="support",
        confirmed_touches=3,
        first_touch_time=candles[14].opened_at,
        most_recent_touch_time=candles[30].opened_at,
        strength_score=80,
        broken=False,
        retested=False,
        higher_timeframe_confluence=False,
    )
    result = detect_trend_lines(_trend_candles(), left_candles=1, right_candles=1, horizontal_zones=[zone])

    assert any(line.direction == "bullish" and line.horizontal_zone_confluence for line in result.lines)


def test_trend_line_endpoint_is_registered():
    paths = {route.path for route in app.routes}
    assert "/api/analysis/trend-lines" in paths

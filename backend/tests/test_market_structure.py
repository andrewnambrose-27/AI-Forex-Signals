from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.market_structure import analyze_market_structure


def _candles(values: list[float], *, final_closed: bool = True):
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        SimpleNamespace(
            opened_at=start + timedelta(minutes=5 * index),
            high=value + 1,
            low=value - 1,
            is_closed=final_closed if index == len(values) - 1 else True,
        )
        for index, value in enumerate(values)
    ]


def test_pivot_is_confirmed_only_after_right_window_closes():
    candles = _candles([10, 14, 12, 11])

    before_confirmation = analyze_market_structure(candles[:3], left_candles=1, right_candles=2)
    after_confirmation = analyze_market_structure(candles, left_candles=1, right_candles=2)

    assert before_confirmation.latest_confirmed_swing_high is None
    assert after_confirmation.latest_confirmed_swing_high is not None
    assert after_confirmation.latest_confirmed_swing_high.index == 1
    assert after_confirmation.latest_confirmed_swing_high.confirmed_at == candles[3].opened_at


def test_open_streaming_candle_cannot_confirm_or_change_a_pivot():
    closed = _candles([10, 14, 12, 11])
    open_preview = SimpleNamespace(
        opened_at=closed[-1].opened_at + timedelta(minutes=5),
        high=100,
        low=-100,
        is_closed=False,
    )

    baseline = analyze_market_structure(closed, left_candles=1, right_candles=2)
    with_preview = analyze_market_structure([*closed, open_preview], left_candles=1, right_candles=2)

    assert with_preview == baseline
    assert with_preview.closed_candle_count == len(closed)


def test_structure_points_and_bullish_state_are_classified_deterministically():
    candles = _candles([10, 14, 12, 8, 11, 15, 13, 9, 12, 16, 14, 10, 13])

    result = analyze_market_structure(candles, left_candles=1, right_candles=1)

    assert [point.classification for point in result.recent_structure_points] == ["HH", "HL", "HH", "HL"]
    assert result.direction == "bullish"
    assert result.confidence_score == 100
    assert result.latest_confirmed_swing_high.price == 17
    assert result.latest_confirmed_swing_low.price == 9


def test_confirmed_points_never_repaint_when_future_candles_are_added():
    candles = _candles([10, 14, 12, 8, 11, 15, 13, 9, 12, 16, 14, 10, 13, 17, 15, 11])
    prefix_size = 12
    prefix = analyze_market_structure(candles[:prefix_size], left_candles=1, right_candles=2)
    full = analyze_market_structure(candles, left_candles=1, right_candles=2)
    cutoff = candles[prefix_size - 1].opened_at

    full_points_known_at_cutoff = [point for point in full.recent_structure_points if point.confirmed_at <= cutoff]
    assert full_points_known_at_cutoff == prefix.recent_structure_points

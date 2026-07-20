from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from app.main import app
from app.services.signal_engine import StrategyEvaluation, StrategyResult, apply_zone_scoring_context
from app.services.support_resistance import detect_support_resistance_zones


def _range_candles():
    values = [
        1.1100,
        1.1200,
        1.1100,
        1.1000,
        1.1100,
        1.1202,
        1.1100,
        1.1002,
        1.1100,
        1.1200,
        1.1100,
        1.1001,
        1.1100,
        1.1199,
        1.1100,
        1.1002,
        1.1100,
        1.1201,
        1.1100,
        1.1000,
        1.1100,
        1.1198,
        1.1100,
        1.1003,
        1.1100,
        1.1202,
        1.1100,
        1.1199,
        1.1100,
        1.1001,
        1.1100,
        1.1201,
        1.1100,
        1.1003,
        1.1100,
        1.1198,
        1.1100,
        1.1002,
        1.1100,
    ]
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        SimpleNamespace(
            opened_at=start + timedelta(minutes=index * 5),
            open=value,
            high=value + 0.0005,
            low=value - 0.0005,
            close=value,
            volume=index * 100,
            is_closed=True,
        )
        for index, value in enumerate(values)
    ]


def test_atr_normalised_zones_cluster_confirmed_touches_without_overlap():
    result = detect_support_resistance_zones(_range_candles(), left_candles=1, right_candles=1, max_zones=8)

    support = next(zone for zone in result.zones if zone.type == "support")
    resistance = next(zone for zone in result.zones if zone.type == "resistance")
    assert result.clustering_distance_atr == 0.25
    assert support.confirmed_touches >= 5
    assert resistance.confirmed_touches >= 5
    assert support.first_touch_time >= _range_candles()[13].opened_at
    assert support.upper_price < resistance.lower_price
    assert len(result.zones) <= 8
    assert support.lower_price < support.centre_price < support.upper_price
    assert 0 <= support.strength_score <= 100


def test_volume_is_not_used_for_zone_detection_or_strength():
    candles = _range_candles()
    without_reliable_volume = [SimpleNamespace(**{**candle.__dict__, "volume": None}) for candle in candles]

    with_volume = detect_support_resistance_zones(candles, left_candles=1, right_candles=1)
    without_volume = detect_support_resistance_zones(without_reliable_volume, left_candles=1, right_candles=1)

    assert with_volume == without_volume


def test_zone_break_requires_closed_buffered_close_and_detects_retest():
    candles = _range_candles()
    next_time = candles[-1].opened_at + timedelta(minutes=5)
    open_break_preview = SimpleNamespace(opened_at=next_time, open=1.1210, high=1.1270, low=1.1210, close=1.1260, is_closed=False)
    before = detect_support_resistance_zones(candles, left_candles=1, right_candles=1, break_buffer_atr=0.1)
    preview = detect_support_resistance_zones([*candles, open_break_preview], left_candles=1, right_candles=1, break_buffer_atr=0.1)
    assert preview == before

    wick_only = SimpleNamespace(**{**open_break_preview.__dict__, "close": 1.1205, "is_closed": True})
    wick_result = detect_support_resistance_zones([*candles, wick_only], left_candles=1, right_candles=1, break_buffer_atr=0.1)
    wick_resistance = next(zone for zone in wick_result.zones if zone.type == "resistance" and zone.confirmed_touches >= 5)
    assert wick_resistance.broken is False

    closed_break = SimpleNamespace(
        **{**open_break_preview.__dict__, "opened_at": next_time + timedelta(minutes=5), "is_closed": True}
    )
    retest = SimpleNamespace(
        opened_at=next_time + timedelta(minutes=10),
        open=1.1240,
        high=1.1250,
        low=1.1205,
        close=1.1230,
        is_closed=True,
    )
    after = detect_support_resistance_zones([*candles, closed_break, retest], left_candles=1, right_candles=1, break_buffer_atr=0.1)
    resistance = next(zone for zone in after.zones if zone.type == "resistance" and zone.confirmed_touches >= 5)

    assert resistance.broken is True
    assert resistance.break_direction == "above"
    assert resistance.retested is True
    assert resistance.broken_at == closed_break.opened_at
    assert resistance.retested_at == retest.opened_at


def test_higher_timeframe_confluence_increases_strength():
    candles = _range_candles()
    base = detect_support_resistance_zones(candles, left_candles=1, right_candles=1)
    with_confluence = detect_support_resistance_zones(
        candles,
        left_candles=1,
        right_candles=1,
        higher_timeframe_zones=base.zones,
    )

    assert all(zone.higher_timeframe_confluence for zone in with_confluence.zones)
    assert all(
        confluent.strength_score >= original.strength_score
        for confluent, original in zip(
            sorted(with_confluence.zones, key=lambda zone: zone.centre_price),
            sorted(base.zones, key=lambda zone: zone.centre_price),
        )
    )


def test_signal_engine_adds_zone_entry_obstruction_breakout_and_retest_components():
    candles = _range_candles()
    candles.append(
        SimpleNamespace(
            opened_at=candles[-1].opened_at + timedelta(minutes=5),
            open=1.1000,
            high=1.1010,
            low=1.0990,
            close=1.1000,
            is_closed=False,
        )
    )
    strategy = StrategyResult(
        strategy="range_mean_reversion",
        direction="BUY",
        score=85,
        reasons=[],
        entry_reference_price=Decimal("1.1000"),
        suggested_stop=Decimal("1.0950"),
        suggested_target=Decimal("1.1250"),
        risk_reward_ratio=Decimal("5"),
    )
    evaluation = StrategyEvaluation(
        pair="EURUSD",
        epic="CS.D.EURUSD.MINI.IP",
        timeframe="5m",
        direction="BUY",
        score=85,
        status="active",
        strategy=strategy.strategy,
        entry_reference_price=strategy.entry_reference_price,
        suggested_stop=strategy.suggested_stop,
        suggested_target=strategy.suggested_target,
        risk_reward_ratio=strategy.risk_reward_ratio,
        reasons=[],
        filters_passed=[],
        filters_failed=[],
        components=[strategy],
    )

    apply_zone_scoring_context(evaluation, primary_candles=candles, higher_candles=[])

    assert strategy.components["entry_near_relevant_zone"] is True
    assert strategy.components["target_obstructed_by_opposing_zone"] is True
    assert "breakout_confirmation" in strategy.components
    assert "retest_confirmation" in strategy.components
    assert any("prior touches" in reason for reason in evaluation.reasons)
    assert any("Signal rejected because resistance" in reason for reason in evaluation.reasons)


def test_zones_endpoint_is_registered():
    assert "/api/analysis/zones" in app.openapi()["paths"]

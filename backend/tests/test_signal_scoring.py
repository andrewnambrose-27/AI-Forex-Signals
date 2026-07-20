from decimal import Decimal

from app.services.signal_engine import StrategyEvaluation, StrategyResult
from app.services.signal_scoring import DEFAULT_SCORING_SETTINGS, SCORE_DISCLAIMER, apply_configurable_scoring


def test_configurable_scoring_uses_default_threshold_and_disclaimer():
    strategy = StrategyResult(
        strategy="trend_continuation",
        direction="BUY",
        score=95,
        components={"ema_alignment": 25, "adx": 30.0, "macd_histogram": 0.0002, "pullback_reclaim": 20},
        filters_passed=["multi_timeframe_ema_alignment"],
        risk_reward_ratio=Decimal("2.0"),
    )
    evaluation = StrategyEvaluation(
        pair="EURUSD",
        epic="CS.D.EURUSD.MINI.IP",
        timeframe="1h",
        direction="BUY",
        score=95,
        status="active",
        strategy="trend_continuation",
        entry_reference_price=Decimal("1.1000"),
        suggested_stop=Decimal("1.0900"),
        suggested_target=Decimal("1.1200"),
        risk_reward_ratio=Decimal("2.0"),
        reasons=[],
        filters_passed=[],
        filters_failed=[],
        components=[strategy],
    )

    result = apply_configurable_scoring(evaluation, settings=DEFAULT_SCORING_SETTINGS)

    assert result.minimum_score == 80
    assert result.score >= 80
    assert len(result.components) == 14
    assert result.components[0].name == "trend_alignment"
    assert result.components[0].max_score == 8
    assert SCORE_DISCLAIMER in result.reasons


def test_news_block_zeroes_news_safety_component():
    strategy = StrategyResult(
        strategy="breakout_volatility_expansion",
        direction="SELL",
        score=85,
        components={"range_break": 30, "atr_expansion": 1.4, "bb_width_percent": 0.01},
        risk_reward_ratio=Decimal("2.2"),
    )
    evaluation = StrategyEvaluation(
        pair="GBPUSD",
        epic="CS.D.GBPUSD.MINI.IP",
        timeframe="5m",
        direction="SELL",
        score=85,
        status="active",
        strategy="breakout_volatility_expansion",
        entry_reference_price=Decimal("1.2500"),
        suggested_stop=Decimal("1.2550"),
        suggested_target=Decimal("1.2390"),
        risk_reward_ratio=Decimal("2.2"),
        reasons=[],
        filters_passed=[],
        filters_failed=[],
        components=[strategy],
    )

    result = apply_configurable_scoring(evaluation, settings=DEFAULT_SCORING_SETTINGS, news_blocked=True)
    news_component = next(component for component in result.components if component.name == "news_safety")

    assert news_component.score == 0
    assert news_component.passed is False


def test_zone_scoring_components_penalise_obstructed_target_and_reward_retest():
    strategy = StrategyResult(
        strategy="breakout_volatility_expansion",
        direction="BUY",
        score=90,
        components={
            "range_break": 30,
            "entry_near_relevant_zone": True,
            "relevant_zone_touches": 4,
            "relevant_zone_type": "support",
            "target_obstructed_by_opposing_zone": True,
            "opposing_zone_r_multiple": 0.6,
            "breakout_confirmation": True,
            "retest_confirmation": True,
        },
        risk_reward_ratio=Decimal("2.0"),
    )
    evaluation = StrategyEvaluation(
        pair="EURUSD",
        epic="CS.D.EURUSD.MINI.IP",
        timeframe="5m",
        direction="BUY",
        score=90,
        status="active",
        strategy=strategy.strategy,
        entry_reference_price=Decimal("1.1000"),
        suggested_stop=Decimal("1.0950"),
        suggested_target=Decimal("1.1100"),
        risk_reward_ratio=Decimal("2.0"),
        reasons=[],
        filters_passed=[],
        filters_failed=[],
        components=[strategy],
    )

    result = apply_configurable_scoring(evaluation, settings=DEFAULT_SCORING_SETTINGS)
    components = {component.name: component for component in result.components}

    assert components["entry_near_relevant_zone"].score == components["entry_near_relevant_zone"].max_score
    assert components["target_obstructed_by_opposing_zone"].score == 0
    assert "0.6R" in components["target_obstructed_by_opposing_zone"].details
    assert components["breakout_confirmation"].passed is True
    assert components["retest_confirmation"].passed is True


def test_trend_line_scoring_components_are_explicit_and_bounded():
    strategy = StrategyResult(
        strategy="trend_continuation",
        direction="BUY",
        score=90,
        components={
            "ema_alignment": 25,
            "valid_trend_line_bounce": True,
            "trend_line_zone_confluence": True,
            "confirmed_trend_line_break": True,
            "failed_trend_line_retest": True,
        },
        risk_reward_ratio=Decimal("2.0"),
    )
    evaluation = StrategyEvaluation(
        pair="EURUSD", epic="CS.D.EURUSD.MINI.IP", timeframe="5m", direction="BUY", score=90,
        status="active", strategy=strategy.strategy, entry_reference_price=Decimal("1.1"),
        suggested_stop=Decimal("1.09"), suggested_target=Decimal("1.12"), risk_reward_ratio=Decimal("2"),
        reasons=[], filters_passed=[], filters_failed=[], components=[strategy],
    )

    result = apply_configurable_scoring(evaluation, settings=DEFAULT_SCORING_SETTINGS)
    components = {component.name: component for component in result.components}
    names = {"valid_trend_line_bounce", "trend_line_zone_confluence", "confirmed_trend_line_break", "failed_trend_line_retest"}

    assert all(components[name].passed for name in names)
    assert sum(component.max_score for component in result.components) == 100


def test_multi_timeframe_conflict_is_an_explicit_negative_penalty():
    strategy = StrategyResult(
        strategy="trend_continuation", direction="BUY", score=90,
        components={"ema_alignment": 25}, risk_reward_ratio=Decimal("2.0"),
    )
    evaluation = StrategyEvaluation(
        pair="EURUSD", epic="TEST", timeframe="5m", direction="BUY", score=90, status="active",
        strategy=strategy.strategy, entry_reference_price=Decimal("1.1"), suggested_stop=Decimal("1.09"),
        suggested_target=Decimal("1.12"), risk_reward_ratio=Decimal("2"), reasons=[], filters_passed=[],
        filters_failed=[], components=[strategy],
    )

    baseline = apply_configurable_scoring(evaluation, settings=DEFAULT_SCORING_SETTINGS)
    conflicted = apply_configurable_scoring(
        evaluation,
        settings=DEFAULT_SCORING_SETTINGS,
        multi_timeframe_penalty=20,
        multi_timeframe_details="Strong 1h conflict.",
    )
    penalty = conflicted.components[-1]

    assert conflicted.score == baseline.score - 20
    assert penalty.name == "multi_timeframe_conflict"
    assert penalty.score == -20
    assert penalty.max_score == 0

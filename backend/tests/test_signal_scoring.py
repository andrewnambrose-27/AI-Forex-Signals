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
    assert len(result.components) == 7
    assert result.components[0].name == "trend_alignment"
    assert result.components[0].max_score == 20
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

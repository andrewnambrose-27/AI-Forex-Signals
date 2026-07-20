from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.services.signal_engine import StrategyEvaluation, StrategyResult


SETTINGS_KEY = "signal_scoring"
DEFAULT_SCORING_SETTINGS = {
    "minimum_score": 80,
    "weights": {
        "trend_alignment": 20,
        "momentum_confirmation": 15,
        "volatility_condition": 15,
        "support_resistance_quality": 15,
        "risk_reward_quality": 15,
        "news_safety": 10,
        "spread_session_quality": 10,
    },
}
SCORE_DISCLAIMER = "Signal score is a rules-based quality score, not a guaranteed win probability."


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    category: str
    score: int
    max_score: int
    passed: bool
    details: str
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class ScoringResult:
    score: int
    minimum_score: int
    components: list[ScoreComponent]
    reasons: list[str]
    filters_passed: list[str]
    filters_failed: list[str]


def get_scoring_settings(db: Session) -> dict[str, Any]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == SETTINGS_KEY))
    if setting is None:
        setting = AppSetting(
            key=SETTINGS_KEY,
            value=DEFAULT_SCORING_SETTINGS.copy(),
            description="Signal component scoring weights and minimum score threshold.",
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return _normalize_settings(setting.value)


def update_scoring_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    current = get_scoring_settings(db)
    next_value = {
        "minimum_score": updates.get("minimum_score", current["minimum_score"]),
        "weights": {**current["weights"], **updates.get("weights", {})},
    }
    setting = db.scalar(select(AppSetting).where(AppSetting.key == SETTINGS_KEY))
    if setting is None:
        setting = AppSetting(key=SETTINGS_KEY, value=next_value)
        db.add(setting)
    else:
        setting.value = next_value
    db.commit()
    return _normalize_settings(next_value)


def apply_configurable_scoring(
    evaluation: StrategyEvaluation,
    *,
    settings: dict[str, Any],
    minimum_score_override: int | None = None,
    news_blocked: bool = False,
) -> ScoringResult:
    normalized_settings = _normalize_settings(settings)
    weights = normalized_settings["weights"]
    minimum_score = minimum_score_override if minimum_score_override is not None else int(normalized_settings["minimum_score"])
    best = _selected_strategy(evaluation)
    components = _score_components(best, weights, news_blocked=news_blocked)
    score = sum(component.score for component in components)
    filters_passed = [component.name for component in components if component.passed]
    filters_failed = [component.name for component in components if not component.passed]
    reasons = _score_reasons(components, score, minimum_score)
    return ScoringResult(
        score=score,
        minimum_score=minimum_score,
        components=components,
        reasons=reasons,
        filters_passed=filters_passed,
        filters_failed=filters_failed,
    )


def _score_components(best: StrategyResult | None, weights: dict[str, int], *, news_blocked: bool) -> list[ScoreComponent]:
    if best is None or best.direction not in {"BUY", "SELL"}:
        return [_component(name, max_score, 0, False, "No qualifying strategy candidate was available.", {}) for name, max_score in weights.items()]

    data = best.components
    rr = float(best.risk_reward_ratio or Decimal("0"))
    trend_components = _score_trend_line_components(best, weights["trend_alignment"])
    momentum_score = _score_momentum(best, weights["momentum_confirmation"])
    volatility_score = _score_volatility(best, weights["volatility_condition"])
    zone_components = _score_zone_components(best, weights["support_resistance_quality"])
    rr_score = _linear_score(rr, 1.2, 2.0, weights["risk_reward_quality"])
    news_score = 0 if news_blocked else weights["news_safety"]
    spread_session_score = weights["spread_session_quality"]

    return [
        *trend_components,
        _component("momentum_confirmation", weights["momentum_confirmation"], momentum_score, momentum_score >= weights["momentum_confirmation"] * 0.6, _detail_momentum(best), data),
        _component("volatility_condition", weights["volatility_condition"], volatility_score, volatility_score >= weights["volatility_condition"] * 0.6, _detail_volatility(best), data),
        *zone_components,
        _component("risk_reward_quality", weights["risk_reward_quality"], rr_score, rr_score >= weights["risk_reward_quality"] * 0.6, f"Risk/reward is {rr:.2f}.", {"risk_reward_ratio": rr}),
        _component("news_safety", weights["news_safety"], news_score, not news_blocked, "No high-impact news block is active." if not news_blocked else "High-impact news window is active.", {}),
        _component("spread_session_quality", weights["spread_session_quality"], spread_session_score, True, "Spread/session checks are using default pass until live spread and session data are added.", {}),
    ]


def _selected_strategy(evaluation: StrategyEvaluation) -> StrategyResult | None:
    if evaluation.strategy:
        for component in evaluation.components:
            if component.strategy == evaluation.strategy:
                return component
    candidates = [component for component in evaluation.components if component.direction in {"BUY", "SELL"}]
    return max(candidates, key=lambda component: component.score, default=None)


def _score_trend(result: StrategyResult, max_score: int) -> int:
    if result.strategy == "trend_continuation":
        return max_score
    if result.components.get("ema_alignment") or "multi_timeframe_ema_alignment" in result.filters_passed:
        return round(max_score * 0.75)
    return round(max_score * 0.35)


def _score_trend_line_components(result: StrategyResult, max_score: int) -> list[ScoreComponent]:
    trend_weight = max(0, max_score)
    alignment_max = trend_weight * 8 // 20
    bounce_max = trend_weight * 3 // 20
    confluence_max = trend_weight * 3 // 20
    break_max = trend_weight * 3 // 20
    retest_max = trend_weight - alignment_max - bounce_max - confluence_max - break_max
    alignment_score = _score_trend(result, alignment_max)
    has_context = "valid_trend_line_bounce" in result.components
    bounce = bool(result.components.get("valid_trend_line_bounce"))
    confluence = bool(result.components.get("trend_line_zone_confluence"))
    trend_break = bool(result.components.get("confirmed_trend_line_break"))
    failed_retest = bool(result.components.get("failed_trend_line_retest"))
    if has_context:
        scores = (bounce_max if bounce else 0, confluence_max if confluence else 0, break_max if trend_break else 0, retest_max if failed_retest else 0)
    else:
        legacy = _score_trend(result, trend_weight)
        denominator = max(trend_weight, 1)
        scores = tuple(round(legacy * weight / denominator) for weight in (bounce_max, confluence_max, break_max, retest_max))
    return [
        _component("trend_alignment", alignment_max, alignment_score, alignment_score >= alignment_max * 0.6, _detail_trend(result), result.components),
        _component("valid_trend_line_bounce", bounce_max, scores[0], bounce, "A closed candle bounced from the relevant active trend line." if bounce else "No relevant closed-candle trend-line bounce is confirmed.", {"confirmed": bounce}),
        _component("trend_line_zone_confluence", confluence_max, scores[1], confluence, "The relevant trend line overlaps a confirmed horizontal zone." if confluence else "No trend-line and horizontal-zone confluence is confirmed.", {"confirmed": confluence}),
        _component("confirmed_trend_line_break", break_max, scores[2], trend_break, "A closed candle broke the opposing trend line beyond its ATR buffer." if trend_break else "No relevant buffered trend-line break is confirmed.", {"confirmed": trend_break}),
        _component("failed_trend_line_retest", retest_max, scores[3], failed_retest, "The broken trend line was retested and not reclaimed on a closed candle." if failed_retest else "No failed trend-line retest is confirmed.", {"confirmed": failed_retest}),
    ]


def _score_momentum(result: StrategyResult, max_score: int) -> int:
    if "macd_histogram" in result.components:
        return max_score if abs(float(result.components["macd_histogram"] or 0)) > 0 else round(max_score * 0.4)
    if "rsi" in result.components:
        return round(max_score * 0.8)
    if "range_break" in result.components:
        return round(max_score * 0.85)
    return round(max_score * 0.5)


def _score_volatility(result: StrategyResult, max_score: int) -> int:
    if result.strategy == "breakout_volatility_expansion":
        return max_score
    if "adx" in result.components and float(result.components["adx"] or 0) >= 18:
        return round(max_score * 0.8)
    return round(max_score * 0.45)


def _score_support_resistance(result: StrategyResult, max_score: int) -> int:
    if result.components.get("pivot_zone_confirmed"):
        return max_score
    if result.components.get("pullback_reclaim") or result.components.get("range_break"):
        return round(max_score * 0.7)
    return round(max_score * 0.35)


def _score_zone_components(result: StrategyResult, max_score: int) -> list[ScoreComponent]:
    zone_weight = max(0, max_score)
    entry_max = zone_weight * 4 // 15
    target_max = zone_weight * 4 // 15
    breakout_max = zone_weight * 4 // 15
    retest_max = zone_weight - entry_max - target_max - breakout_max
    entry_near = bool(result.components.get("entry_near_relevant_zone"))
    obstructed = bool(result.components.get("target_obstructed_by_opposing_zone"))
    breakout = bool(result.components.get("breakout_confirmation"))
    retest = bool(result.components.get("retest_confirmation"))
    touches = int(result.components.get("relevant_zone_touches") or 0)
    opposing_r = result.components.get("opposing_zone_r_multiple")
    if "entry_near_relevant_zone" not in result.components:
        legacy_score = _score_support_resistance(result, max_score)
        denominator = max(max_score, 1)
        entry_score = round(legacy_score * entry_max / denominator)
        target_score = round(legacy_score * target_max / denominator)
        breakout_score = round(legacy_score * breakout_max / denominator)
        retest_score = max(0, legacy_score - entry_score - target_score - breakout_score)
    else:
        entry_score = entry_max if entry_near else 0
        target_score = 0 if obstructed else target_max
        breakout_score = breakout_max if breakout else 0
        retest_score = retest_max if retest else 0
    return [
        _component(
            "entry_near_relevant_zone",
            entry_max,
            entry_score,
            entry_near,
            f"Entry is near a relevant zone confirmed by {touches} prior touches." if entry_near else "Entry is not near a relevant confirmed zone.",
            {"touches": touches, "zone_type": result.components.get("relevant_zone_type")},
        ),
        _component(
            "target_obstructed_by_opposing_zone",
            target_max,
            target_score,
            not obstructed,
            f"Target is obstructed by an opposing zone {float(opposing_r):.1f}R from entry." if obstructed and opposing_r is not None else "No confirmed opposing zone obstructs the target.",
            {"obstructed": obstructed, "distance_r": opposing_r},
        ),
        _component(
            "breakout_confirmation",
            breakout_max,
            breakout_score,
            breakout,
            "A closed candle broke the zone beyond its ATR buffer." if breakout else "No relevant buffered zone breakout is confirmed.",
            {"confirmed": breakout},
        ),
        _component(
            "retest_confirmation",
            retest_max,
            retest_score,
            retest,
            "A broken zone was retested successfully on a closed candle." if retest else "No confirmed break-and-retest is present.",
            {"confirmed": retest},
        ),
    ]


def _linear_score(value: float, low: float, high: float, max_score: int) -> int:
    if value <= low:
        return 0
    if value >= high:
        return max_score
    return round(((value - low) / (high - low)) * max_score)


def _component(name: str, max_score: int, score: int, passed: bool, details: str, raw_data: dict[str, Any]) -> ScoreComponent:
    return ScoreComponent(
        name=name,
        category="scoring",
        score=max(0, min(max_score, round(score))),
        max_score=max_score,
        passed=passed,
        details=details,
        raw_data=raw_data,
    )


def _score_reasons(components: list[ScoreComponent], score: int, minimum_score: int) -> list[str]:
    strongest = [component for component in components if component.score >= component.max_score * 0.8]
    weakest = [component for component in components if component.score < component.max_score * 0.5]
    reasons = [f"Overall quality score is {score}/100 versus the configured minimum of {minimum_score}."]
    if strongest:
        reasons.append("Strong areas: " + ", ".join(component.name.replace("_", " ") for component in strongest[:3]) + ".")
    if weakest:
        reasons.append("Weak areas: " + ", ".join(component.name.replace("_", " ") for component in weakest[:3]) + ".")
    reasons.append(SCORE_DISCLAIMER)
    return reasons


def _detail_trend(result: StrategyResult) -> str:
    return "Trend alignment is strongest for trend continuation setups." if result.strategy == "trend_continuation" else "Trend alignment is present but not the primary setup type."


def _detail_momentum(result: StrategyResult) -> str:
    if "macd_histogram" in result.components:
        return f"MACD histogram is {result.components['macd_histogram']}."
    if "rsi" in result.components:
        return f"RSI is {result.components['rsi']}."
    return "Momentum is inferred from the active strategy confirmation."


def _detail_volatility(result: StrategyResult) -> str:
    if "atr_expansion" in result.components:
        return f"ATR expansion ratio is {result.components['atr_expansion']}."
    if "adx" in result.components:
        return f"ADX is {result.components['adx']}."
    return "Volatility condition is inferred from the strategy setup."


def _detail_support_resistance(result: StrategyResult) -> str:
    if result.components.get("pivot_zone_confirmed"):
        return "Price is reacting near a confirmed pivot zone."
    if result.components.get("range_break"):
        return "Price broke a recent support/resistance range."
    if result.components.get("pullback_reclaim"):
        return "Price reclaimed the pullback level on a closed candle."
    return "Support/resistance quality is limited for this setup."


def _normalize_settings(value: dict[str, Any]) -> dict[str, Any]:
    weights = {**DEFAULT_SCORING_SETTINGS["weights"], **value.get("weights", {})}
    return {
        "minimum_score": int(value.get("minimum_score", DEFAULT_SCORING_SETTINGS["minimum_score"])),
        "weights": {key: int(score) for key, score in weights.items()},
    }

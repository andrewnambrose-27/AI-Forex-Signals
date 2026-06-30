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
    trend_score = _score_trend(best, weights["trend_alignment"])
    momentum_score = _score_momentum(best, weights["momentum_confirmation"])
    volatility_score = _score_volatility(best, weights["volatility_condition"])
    sr_score = _score_support_resistance(best, weights["support_resistance_quality"])
    rr_score = _linear_score(rr, 1.2, 2.0, weights["risk_reward_quality"])
    news_score = 0 if news_blocked else weights["news_safety"]
    spread_session_score = weights["spread_session_quality"]

    return [
        _component("trend_alignment", weights["trend_alignment"], trend_score, trend_score >= weights["trend_alignment"] * 0.6, _detail_trend(best), data),
        _component("momentum_confirmation", weights["momentum_confirmation"], momentum_score, momentum_score >= weights["momentum_confirmation"] * 0.6, _detail_momentum(best), data),
        _component("volatility_condition", weights["volatility_condition"], volatility_score, volatility_score >= weights["volatility_condition"] * 0.6, _detail_volatility(best), data),
        _component("support_resistance_quality", weights["support_resistance_quality"], sr_score, sr_score >= weights["support_resistance_quality"] * 0.6, _detail_support_resistance(best), data),
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

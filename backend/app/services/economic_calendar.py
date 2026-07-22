from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.app_setting import AppSetting
from app.models.economic_event import EconomicEvent
from app.services.calendar_providers.base import CalendarProviderError, EconomicCalendarProvider, ProviderHealth
from app.services.calendar_providers.fmp import FMPEconomicCalendarProvider


SETTINGS_KEY = "calendar_risk_filter"
SYNC_STATUS_KEY = "calendar_sync_status"
PAIR_CURRENCIES = {
    "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"], "USDJPY": ["USD", "JPY"],
    "AUDUSD": ["AUD", "USD"], "USDCAD": ["USD", "CAD"], "USDCHF": ["USD", "CHF"],
    "NZDUSD": ["NZD", "USD"], "EURGBP": ["EUR", "GBP"],
}
COUNTRY_CURRENCY = {
    "united states": "USD", "us": "USD", "usa": "USD", "eurozone": "EUR", "european union": "EUR",
    "united kingdom": "GBP", "uk": "GBP", "japan": "JPY", "australia": "AUD", "canada": "CAD",
    "switzerland": "CHF", "new zealand": "NZD", "germany": "EUR", "france": "EUR", "italy": "EUR",
    "spain": "EUR",
}
HIGH_IMPACT_PATTERNS = (
    r"interest\s+rate", r"rate\s+decision", r"monetary\s+policy", r"press\s+conference",
    r"\bcpi\b", r"inflation", r"nonfarm|non-farm|\bnfp\b", r"unemployment\s+rate", r"\bgdp\b",
    r"\bpce\b", r"employment\s+(change|report|situation)", r"payroll",
)
MEDIUM_IMPACT_PATTERNS = (
    r"retail\s+sales", r"\bpmi\b", r"industrial\s+production", r"jobless\s+claims", r"consumer\s+confidence",
)


@dataclass(frozen=True)
class CalendarEventPayload:
    provider: str
    provider_event_id: str | None
    title: str
    country: str | None
    currency: str
    event_time_utc: datetime
    impact: str
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    revised_previous: str | None = None
    unit: str | None = None
    source: str | None = None
    status: str = "scheduled"
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class PairRisk:
    pair: str
    currencies: list[str]
    blocked: bool
    reason: str | None
    block_before_minutes: int
    block_after_minutes: int
    event: EconomicEvent | None
    upcoming_events: list[EconomicEvent]
    calendar_status: str
    last_synced_at: datetime | None


@dataclass(frozen=True)
class CalendarStatus:
    provider: str
    calendar_status: str
    configured: bool
    last_sync_attempt_at: datetime | None
    last_successful_sync_at: datetime | None
    next_sync_due_at: datetime | None
    last_error: str | None
    stored_event_count: int
    upcoming_event_count: int
    sync_interval_minutes: int


class UnavailableCalendarProvider(EconomicCalendarProvider):
    def __init__(self, name: str) -> None:
        self.name = name

    def fetch_events(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        raise CalendarProviderError(f"Economic calendar provider '{self.name}' is not implemented")

    def normalize_event(self, raw_event: dict[str, Any]) -> Any:
        raise CalendarProviderError(f"Economic calendar provider '{self.name}' is not implemented")

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(self.name, False, False, f"Provider '{self.name}' is unavailable")


def default_calendar_settings() -> dict[str, Any]:
    settings = get_settings()
    return {
        "provider": settings.economic_calendar_provider.lower(),
        "sync_interval_minutes": settings.news_sync_interval_minutes,
        "block_before_high_minutes": settings.news_block_before_high_minutes,
        "block_after_high_minutes": settings.news_block_after_high_minutes,
        "block_before_medium_minutes": settings.news_block_before_medium_minutes,
        "block_after_medium_minutes": settings.news_block_after_medium_minutes,
    }


def get_calendar_settings(db: Session) -> dict[str, Any]:
    defaults = default_calendar_settings()
    setting = db.scalar(select(AppSetting).where(AppSetting.key == SETTINGS_KEY))
    if setting is None:
        setting = AppSetting(key=SETTINGS_KEY, value=defaults, description="Economic calendar provider, sync interval, and news block windows.")
        db.add(setting)
        db.commit()
    value = dict(setting.value or {})
    # Preserve compatibility with the original setting names.
    if "block_before_high_impact_minutes" in value:
        value["block_before_high_minutes"] = value["block_before_high_impact_minutes"]
    if "block_after_high_impact_minutes" in value:
        value["block_after_high_minutes"] = value["block_after_high_impact_minutes"]
    result = {**defaults, **value}
    result["block_before_high_impact_minutes"] = result["block_before_high_minutes"]
    result["block_after_high_impact_minutes"] = result["block_after_high_minutes"]
    return result


def update_calendar_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(updates)
    if "block_before_high_impact_minutes" in normalized:
        normalized["block_before_high_minutes"] = normalized.pop("block_before_high_impact_minutes")
    if "block_after_high_impact_minutes" in normalized:
        normalized["block_after_high_minutes"] = normalized.pop("block_after_high_impact_minutes")
    next_value = {**get_calendar_settings(db), **{key: value for key, value in normalized.items() if value is not None}}
    next_value["block_before_high_impact_minutes"] = next_value["block_before_high_minutes"]
    next_value["block_after_high_impact_minutes"] = next_value["block_after_high_minutes"]
    _save_setting(db, SETTINGS_KEY, next_value, "Economic calendar provider, sync interval, and news block windows.")
    db.commit()
    return next_value


def get_calendar_provider(provider_name: str | None = None) -> EconomicCalendarProvider:
    name = (provider_name or get_settings().economic_calendar_provider).lower()
    if name == "fmp":
        return FMPEconomicCalendarProvider(get_settings().fmp_api_key)
    return UnavailableCalendarProvider(name)


def sync_events(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    provider: EconomicCalendarProvider | None = None,
) -> list[EconomicEvent]:
    settings = get_calendar_settings(db)
    selected = provider or get_calendar_provider(str(settings["provider"]))
    attempt_time = _now_utc()
    try:
        raw_events = selected.fetch_events(start_date, end_date)
        normalized: list[CalendarEventPayload] = []
        errors: list[str] = []
        for raw in raw_events:
            try:
                normalized.append(selected.normalize_event(raw))
            except (CalendarProviderError, ValueError, TypeError) as exc:
                errors.append(str(exc))
        if raw_events and not normalized:
            raise CalendarProviderError(f"Provider returned {len(raw_events)} event(s), but none could be normalized: {errors[0] if errors else 'unknown error'}")
        events = [_upsert_event(db, payload) for payload in normalized]
        db.flush()
        _write_sync_status(db, attempt=attempt_time, success=_now_utc(), error=None, event_count=len(events), provider=selected.name)
        db.commit()
        return sorted(events, key=lambda event: event.event_time)
    except Exception as exc:
        db.rollback()
        _write_sync_status(db, attempt=attempt_time, success=None, error=_safe_error(exc), event_count=0, provider=selected.name)
        db.commit()
        if isinstance(exc, CalendarProviderError):
            raise
        raise CalendarProviderError(f"Economic calendar sync failed: {exc}") from exc


def sync_if_due(db: Session, *, now: datetime | None = None) -> bool:
    current = _ensure_aware(now or _now_utc())
    settings = get_calendar_settings(db)
    sync_state = _sync_state(db)
    last_attempt = _parse_optional_datetime(sync_state.get("last_attempt_at"))
    interval = timedelta(minutes=int(settings["sync_interval_minutes"]))
    if last_attempt and current < last_attempt + interval:
        return False
    try:
        sync_events(db, start_date=(current - timedelta(days=1)).date(), end_date=(current + timedelta(days=7)).date())
    except CalendarProviderError:
        return False
    return True


def upcoming_events(db: Session, currencies: list[str] | None = None, limit: int = 100, *, sync: bool = True) -> list[EconomicEvent]:
    if sync:
        sync_if_due(db)
    query = select(EconomicEvent).where(EconomicEvent.event_time >= _now_utc(), EconomicEvent.status != "cancelled")
    if currencies:
        query = query.where(EconomicEvent.currency.in_([currency.upper() for currency in currencies]))
    return list(db.scalars(query.order_by(EconomicEvent.event_time.asc()).limit(limit)))


def events_for_currency(db: Session, currency: str, days: int, *, now: datetime | None = None) -> list[EconomicEvent]:
    current = _ensure_aware(now or _now_utc())
    sync_if_due(db, now=current)
    return list(db.scalars(
        select(EconomicEvent).where(
            EconomicEvent.currency == currency.upper(),
            EconomicEvent.event_time >= current,
            EconomicEvent.event_time <= current + timedelta(days=days),
        ).order_by(EconomicEvent.event_time.asc())
    ))


def calendar_status(db: Session, *, now: datetime | None = None) -> CalendarStatus:
    current = _ensure_aware(now or _now_utc())
    settings = get_calendar_settings(db)
    state = _sync_state(db)
    last_attempt = _parse_optional_datetime(state.get("last_attempt_at"))
    last_success = _parse_optional_datetime(state.get("last_success_at"))
    interval_minutes = int(settings["sync_interval_minutes"])
    total = int(db.scalar(select(func.count(EconomicEvent.id))) or 0)
    upcoming = int(db.scalar(select(func.count(EconomicEvent.id)).where(EconomicEvent.event_time >= current, EconomicEvent.status != "cancelled")) or 0)
    provider = get_calendar_provider(str(settings["provider"]))
    configured = not isinstance(provider, UnavailableCalendarProvider) and not (isinstance(provider, FMPEconomicCalendarProvider) and not provider.api_key)
    stale_after = timedelta(minutes=max(1, interval_minutes * 2))
    if not configured or last_success is None or total == 0 or upcoming == 0:
        status = "unavailable"
    elif current - last_success > stale_after:
        status = "stale"
    else:
        status = "healthy"
    return CalendarStatus(
        provider=str(settings["provider"]), calendar_status=status, configured=configured,
        last_sync_attempt_at=last_attempt, last_successful_sync_at=last_success,
        next_sync_due_at=last_attempt + timedelta(minutes=interval_minutes) if last_attempt else current,
        last_error=state.get("last_error"), stored_event_count=total, upcoming_event_count=upcoming,
        sync_interval_minutes=interval_minutes,
    )


def evaluate_pair_news_risk(db: Session, pair: str, now: datetime | None = None) -> PairRisk:
    current = _ensure_aware(now or _now_utc())
    sync_if_due(db, now=current)
    status = calendar_status(db, now=current)
    currencies = currencies_for_pair(pair)
    settings = get_calendar_settings(db)
    events = upcoming_events(db, currencies=currencies, limit=50, sync=False)
    maximum_before = max(int(settings["block_before_high_minutes"]), int(settings["block_before_medium_minutes"]))
    maximum_after = max(int(settings["block_after_high_minutes"]), int(settings["block_after_medium_minutes"]))
    candidates = list(db.scalars(
        select(EconomicEvent).where(
            EconomicEvent.currency.in_(currencies), EconomicEvent.impact.in_(["high", "medium"]),
            EconomicEvent.status != "cancelled",
            EconomicEvent.event_time >= current - timedelta(minutes=maximum_after),
            EconomicEvent.event_time <= current + timedelta(minutes=maximum_before),
        ).order_by(EconomicEvent.event_time.asc())
    ))
    for event in candidates:
        before = int(settings[f"block_before_{event.impact}_minutes"])
        after = int(settings[f"block_after_{event.impact}_minutes"])
        event_time = _ensure_aware(event.event_time)
        if event_time - timedelta(minutes=before) <= current <= event_time + timedelta(minutes=after):
            return PairRisk(
                pair=_normalize_pair(pair), currencies=currencies, blocked=True,
                reason=f"{event.impact.capitalize()}-impact {event.currency} event: {event.title}",
                block_before_minutes=before, block_after_minutes=after, event=event, upcoming_events=events,
                calendar_status=status.calendar_status, last_synced_at=status.last_successful_sync_at,
            )
    if status.calendar_status != "healthy":
        return PairRisk(
            pair=_normalize_pair(pair), currencies=currencies, blocked=True,
            reason=f"Economic calendar data is {status.calendar_status}; news risk cannot be considered safe.",
            block_before_minutes=int(settings["block_before_high_minutes"]),
            block_after_minutes=int(settings["block_after_high_minutes"]), event=None,
            upcoming_events=events, calendar_status=status.calendar_status, last_synced_at=status.last_successful_sync_at,
        )
    return PairRisk(
        pair=_normalize_pair(pair), currencies=currencies, blocked=False, reason=None,
        block_before_minutes=int(settings["block_before_high_minutes"]),
        block_after_minutes=int(settings["block_after_high_minutes"]), event=None, upcoming_events=events,
        calendar_status=status.calendar_status, last_synced_at=status.last_successful_sync_at,
    )


def currencies_for_pair(pair: str) -> list[str]:
    normalized = _normalize_pair(pair)
    if normalized in PAIR_CURRENCIES:
        return PAIR_CURRENCIES[normalized]
    return [normalized[:3], normalized[3:6]] if len(normalized) == 6 else []


def classify_event_impact(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    if any(re.search(pattern, normalized) for pattern in HIGH_IMPACT_PATTERNS):
        return "high"
    if any(re.search(pattern, normalized) for pattern in MEDIUM_IMPACT_PATTERNS):
        return "medium"
    return "unknown"


def country_currency(country: str | None) -> str | None:
    return COUNTRY_CURRENCY.get((country or "").strip().lower())


def fallback_dedupe_key(title: str, country: str | None, event_time: datetime) -> str:
    normalized_title = re.sub(r"\s+", " ", title.strip().lower())
    normalized_country = (country or "").strip().lower()
    utc_time = _ensure_aware(event_time).replace(second=0, microsecond=0).isoformat()
    return sha256(f"{normalized_title}|{normalized_country}|{utc_time}".encode("utf-8")).hexdigest()


def _upsert_event(db: Session, payload: CalendarEventPayload) -> EconomicEvent:
    event_time = _ensure_aware(payload.event_time_utc)
    dedupe_key = fallback_dedupe_key(payload.title, payload.country, event_time)
    provider_id = payload.provider_event_id.strip() if payload.provider_event_id else None
    clauses = [EconomicEvent.fallback_dedupe_key == dedupe_key]
    if provider_id:
        clauses.append(EconomicEvent.provider_event_id == provider_id)
    existing = db.scalar(select(EconomicEvent).where(EconomicEvent.provider == payload.provider, or_(*clauses)))
    values = {
        "provider": payload.provider, "external_id": provider_id, "provider_event_id": provider_id,
        "fallback_dedupe_key": None if provider_id else dedupe_key, "country": payload.country, "currency": payload.currency.upper(),
        "title": payload.title, "impact": payload.impact if payload.impact in {"low", "medium", "high", "unknown"} else classify_event_impact(payload.title),
        "event_time": event_time, "actual": payload.actual, "forecast": payload.forecast, "previous": payload.previous,
        "revised_previous": payload.revised_previous, "unit": payload.unit, "source": payload.source,
        "status": payload.status if payload.status in {"scheduled", "released", "revised", "cancelled"} else "scheduled",
        "raw_data": payload.raw_payload, "raw_payload": payload.raw_payload,
    }
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    event = EconomicEvent(**values)
    db.add(event)
    return event


def _sync_state(db: Session) -> dict[str, Any]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == SYNC_STATUS_KEY))
    return dict(setting.value or {}) if setting else {}


def _write_sync_status(db: Session, *, attempt: datetime, success: datetime | None, error: str | None, event_count: int, provider: str) -> None:
    previous = _sync_state(db)
    value = {
        "provider": provider, "last_attempt_at": attempt.isoformat(),
        "last_success_at": success.isoformat() if success else previous.get("last_success_at"),
        "last_error": error, "last_event_count": event_count,
    }
    _save_setting(db, SYNC_STATUS_KEY, value, "Economic calendar synchronization health; contains no provider secrets.")


def _save_setting(db: Session, key: str, value: dict[str, Any], description: str) -> None:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting is None:
        db.add(AppSetting(key=key, value=value, description=description))
    else:
        setting.value = value


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    api_key = get_settings().fmp_api_key
    return message.replace(api_key, "[redacted]")[:500] if api_key else message[:500]


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    try:
        return _ensure_aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _normalize_pair(pair: str) -> str:
    return pair.replace("/", "").replace("-", "").replace("_", "").upper()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

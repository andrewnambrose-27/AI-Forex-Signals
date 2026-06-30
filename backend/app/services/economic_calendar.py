from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.models.economic_event import EconomicEvent


SETTINGS_KEY = "calendar_risk_filter"
DEFAULT_CALENDAR_SETTINGS = {
    "provider": "mock",
    "block_before_high_impact_minutes": 60,
    "block_after_high_impact_minutes": 30,
}

COUNTRY_BY_CURRENCY = {
    "USD": "United States",
    "EUR": "Eurozone",
    "GBP": "United Kingdom",
    "JPY": "Japan",
    "AUD": "Australia",
    "CAD": "Canada",
    "CHF": "Switzerland",
    "NZD": "New Zealand",
}


@dataclass(frozen=True)
class CalendarEventPayload:
    provider: str
    external_id: str
    country: str | None
    currency: str
    title: str
    impact: str
    event_time: datetime
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    notes: str | None = None
    raw_data: dict[str, Any] | None = None


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


class CalendarProvider(Protocol):
    name: str

    def fetch_upcoming(self, currencies: list[str] | None = None) -> list[CalendarEventPayload]:
        ...


class MockCalendarProvider:
    name = "mock"

    def fetch_upcoming(self, currencies: list[str] | None = None) -> list[CalendarEventPayload]:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        wanted = set(currencies or COUNTRY_BY_CURRENCY.keys())
        templates = [
            ("USD", "United States", "FOMC statement", "high", 75, None, "5.50%", "5.50%"),
            ("USD", "United States", "Initial jobless claims", "medium", 210, "221K", "220K", "218K"),
            ("EUR", "Eurozone", "ECB monetary policy meeting accounts", "high", 150, None, None, None),
            ("GBP", "United Kingdom", "UK CPI y/y", "high", 95, "2.1%", "2.0%", "2.3%"),
            ("JPY", "Japan", "Tokyo core CPI y/y", "medium", 360, "2.0%", "2.1%", "2.0%"),
            ("AUD", "Australia", "RBA rate statement", "high", 260, None, "4.35%", "4.35%"),
            ("CAD", "Canada", "Employment change", "high", 315, "18K", "20K", "27K"),
            ("CHF", "Switzerland", "SNB policy rate", "high", 420, None, "1.25%", "1.25%"),
        ]

        events: list[CalendarEventPayload] = []
        for currency, country, title, impact, minutes, actual, forecast, previous in templates:
            if currency not in wanted:
                continue
            event_time = now + timedelta(minutes=minutes)
            events.append(
                CalendarEventPayload(
                    provider=self.name,
                    external_id=f"mock-{currency}-{event_time:%Y%m%d%H%M}",
                    country=country,
                    currency=currency,
                    title=title,
                    impact=impact,
                    event_time=event_time,
                    actual=actual,
                    forecast=forecast,
                    previous=previous,
                    raw_data={"source": "mock", "minutes_from_now": minutes},
                )
            )
        return events


class UnconfiguredCalendarProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    def fetch_upcoming(self, currencies: list[str] | None = None) -> list[CalendarEventPayload]:
        return []


def get_calendar_settings(db: Session) -> dict[str, Any]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == SETTINGS_KEY))
    if setting is None:
        setting = AppSetting(
            key=SETTINGS_KEY,
            value=DEFAULT_CALENDAR_SETTINGS.copy(),
            description="Economic calendar provider and high-impact news block windows.",
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return {**DEFAULT_CALENDAR_SETTINGS, **setting.value}


def update_calendar_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    current = get_calendar_settings(db)
    next_value = {**current, **{key: value for key, value in updates.items() if value is not None}}
    setting = db.scalar(select(AppSetting).where(AppSetting.key == SETTINGS_KEY))
    if setting is None:
        setting = AppSetting(key=SETTINGS_KEY, value=next_value)
        db.add(setting)
    else:
        setting.value = next_value
    db.commit()
    return next_value


def get_calendar_provider(provider_name: str) -> CalendarProvider:
    normalized = provider_name.lower()
    if normalized == "mock":
        return MockCalendarProvider()
    return UnconfiguredCalendarProvider(normalized)


def sync_upcoming_events(db: Session, currencies: list[str] | None = None) -> list[EconomicEvent]:
    settings = get_calendar_settings(db)
    provider = get_calendar_provider(str(settings["provider"]))
    payloads = provider.fetch_upcoming(currencies=currencies)
    events = [_upsert_event(db, payload) for payload in payloads]
    db.commit()
    return sorted(events, key=lambda event: event.event_time)


def upcoming_events(db: Session, currencies: list[str] | None = None, limit: int = 100) -> list[EconomicEvent]:
    sync_upcoming_events(db, currencies=currencies)
    query = select(EconomicEvent).where(EconomicEvent.event_time >= _now_utc())
    if currencies:
        query = query.where(EconomicEvent.currency.in_([currency.upper() for currency in currencies]))
    return list(db.scalars(query.order_by(EconomicEvent.event_time.asc()).limit(limit)))


def evaluate_pair_news_risk(db: Session, pair: str, now: datetime | None = None) -> PairRisk:
    settings = get_calendar_settings(db)
    currencies = currencies_for_pair(pair)
    events = upcoming_events(db, currencies=currencies, limit=50)
    now_utc = _ensure_aware(now or _now_utc())
    before_minutes = int(settings["block_before_high_impact_minutes"])
    after_minutes = int(settings["block_after_high_impact_minutes"])
    window_start = now_utc - timedelta(minutes=after_minutes)
    window_end = now_utc + timedelta(minutes=before_minutes)
    risk_events = list(
        db.scalars(
            select(EconomicEvent)
            .where(
                EconomicEvent.currency.in_(currencies),
                EconomicEvent.impact == "high",
                EconomicEvent.event_time >= window_start,
                EconomicEvent.event_time <= window_end,
            )
            .order_by(EconomicEvent.event_time.asc())
        )
    )

    for event in risk_events:
        event_time = _ensure_aware(event.event_time)
        event_window_start = event_time - timedelta(minutes=before_minutes)
        event_window_end = event_time + timedelta(minutes=after_minutes)
        if event_window_start <= now_utc <= event_window_end:
            return PairRisk(
                pair=pair.upper(),
                currencies=currencies,
                blocked=True,
                reason=f"High-impact {event.currency} event: {event.title}",
                block_before_minutes=before_minutes,
                block_after_minutes=after_minutes,
                event=event,
                upcoming_events=events,
            )

    return PairRisk(
        pair=pair.upper(),
        currencies=currencies,
        blocked=False,
        reason=None,
        block_before_minutes=before_minutes,
        block_after_minutes=after_minutes,
        event=None,
        upcoming_events=events,
    )


def currencies_for_pair(pair: str) -> list[str]:
    normalized = pair.replace("/", "").replace("-", "").replace("_", "").upper()
    if len(normalized) < 6:
        return [normalized] if normalized else []
    return [normalized[:3], normalized[3:6]]


def _upsert_event(db: Session, payload: CalendarEventPayload) -> EconomicEvent:
    existing = db.scalar(
        select(EconomicEvent).where(
            EconomicEvent.provider == payload.provider,
            EconomicEvent.external_id == payload.external_id,
        )
    )
    values = {
        "provider": payload.provider,
        "external_id": payload.external_id,
        "country": payload.country,
        "currency": payload.currency.upper(),
        "title": payload.title,
        "impact": payload.impact.lower(),
        "event_time": payload.event_time,
        "actual": payload.actual,
        "forecast": payload.forecast,
        "previous": payload.previous,
        "notes": payload.notes,
        "raw_data": payload.raw_data,
    }
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    event = EconomicEvent(**values)
    db.add(event)
    return event


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

from datetime import date, datetime, timedelta, timezone
import os

import httpx
import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.main import app
from app.models.app_setting import AppSetting
from app.models.economic_event import EconomicEvent
from app.services import economic_calendar as calendar_service
from app.services.calendar_providers.base import CalendarProviderError, EconomicCalendarProvider, ProviderHealth
from app.services.calendar_providers.fmp import FMPEconomicCalendarProvider
from app.services.economic_calendar import (
    CalendarEventPayload, calendar_status, classify_event_impact, currencies_for_pair,
    evaluate_pair_news_risk, fallback_dedupe_key, get_calendar_settings, sync_events,
    sync_if_due, update_calendar_settings,
)


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_currencies_for_pair_maps_major_pairs():
    assert currencies_for_pair("GBPUSD") == ["GBP", "USD"]
    assert currencies_for_pair("EUR/USD") == ["EUR", "USD"]


def test_calendar_settings_default_and_update():
    db = make_session()

    settings = get_calendar_settings(db)
    assert settings["block_before_high_impact_minutes"] == 60

    updated = update_calendar_settings(db, {"block_before_high_impact_minutes": 90})
    assert updated["block_before_high_impact_minutes"] == 90
    assert db.query(AppSetting).filter(AppSetting.key == "calendar_risk_filter").count() == 1


def test_pair_risk_blocks_inside_high_impact_window():
    db = make_session()
    update_calendar_settings(
        db,
        {
            "provider": "none",
            "block_before_high_impact_minutes": 60,
            "block_after_high_impact_minutes": 30,
        },
    )
    event_time = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    db.add(
        EconomicEvent(
            provider="test",
            external_id="gbp-cpi",
            country="United Kingdom",
            currency="GBP",
            title="UK CPI y/y",
            impact="high",
            event_time=event_time,
        )
    )
    db.commit()

    risk = evaluate_pair_news_risk(db, "GBPUSD", now=event_time - timedelta(minutes=45))

    assert risk.blocked is True
    assert risk.event is not None
    assert risk.event.title == "UK CPI y/y"
    assert risk.reason == "High-impact GBP event: UK CPI y/y"


def test_pair_risk_allows_outside_high_impact_window():
    db = make_session()
    update_calendar_settings(db, {"provider": "none"})
    event_time = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    db.add(
        EconomicEvent(
            provider="test",
            external_id="usd-fomc",
            country="United States",
            currency="USD",
            title="FOMC statement",
            impact="high",
            event_time=event_time,
        )
    )
    db.commit()

    risk = evaluate_pair_news_risk(db, "EURUSD", now=event_time - timedelta(hours=3))

    assert risk.blocked is True
    assert risk.event is None
    assert risk.calendar_status == "unavailable"
    assert "cannot be considered safe" in risk.reason


class FakeProvider(EconomicCalendarProvider):
    name = "fake"

    def __init__(self, events: list[dict] | None = None, *, error: str | None = None) -> None:
        self.events = events or []
        self.error = error

    def fetch_events(self, start_date: date, end_date: date) -> list[dict]:
        if self.error:
            raise CalendarProviderError(self.error)
        return self.events

    def normalize_event(self, raw_event: dict) -> CalendarEventPayload:
        return CalendarEventPayload(**raw_event)

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(self.name, not self.error, True, self.error or "ok")


def _payload(event_time: datetime, **updates) -> dict:
    values = {
        "provider": "fake", "provider_event_id": "event-1", "title": "US CPI y/y",
        "country": "United States", "currency": "USD", "event_time_utc": event_time,
        "impact": "high", "forecast": "2.7%", "previous": "2.8%", "source": "test",
        "raw_payload": {"test": True},
    }
    values.update(updates)
    return values


@pytest.mark.parametrize(
    ("title", "impact"),
    [
        ("Federal Reserve Interest Rate Decision", "high"), ("Nonfarm Payrolls", "high"),
        ("Core PCE Inflation", "high"), ("Manufacturing PMI", "medium"),
        ("Initial Jobless Claims", "medium"), ("Wholesale Inventories", "unknown"),
    ],
)
def test_fallback_impact_classifier_is_deterministic(title: str, impact: str):
    assert classify_event_impact(title) == impact


def test_fmp_provider_uses_header_auth_and_normalizes_utc_event():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=[{
            "id": "fmp-123", "date": "2026-07-22T12:30:00Z", "country": "US", "currency": "USD",
            "event": "Consumer Price Index", "impact": "High", "actual": "2.6%", "estimate": "2.7%",
            "previous": "2.8%", "unit": "%",
        }])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = FMPEconomicCalendarProvider("secret-key", client=client)
    raw = provider.fetch_events(date(2026, 7, 22), date(2026, 7, 23))[0]
    event = provider.normalize_event(raw)

    assert captured[0].headers["apikey"] == "secret-key"
    assert "secret-key" not in str(captured[0].url)
    assert event.provider_event_id == "fmp-123"
    assert event.event_time_utc == datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc)
    assert event.impact == "high"
    assert event.status == "released"


def test_fmp_health_check_reports_missing_key_without_network_call():
    health = FMPEconomicCalendarProvider(None).health_check()
    assert health.healthy is False
    assert health.configured is False


def test_sync_deduplicates_provider_id_and_updates_release_values(monkeypatch):
    db = make_session()
    event_time = datetime.now(timezone.utc) + timedelta(hours=2)
    provider = FakeProvider([_payload(event_time)])
    monkeypatch.setattr(calendar_service, "get_calendar_provider", lambda name=None: provider)

    sync_events(db, start_date=date.today(), end_date=date.today() + timedelta(days=1), provider=provider)
    provider.events = [_payload(event_time, actual="2.6%", revised_previous="2.9%", status="revised")]
    sync_events(db, start_date=date.today(), end_date=date.today() + timedelta(days=1), provider=provider)

    events = db.query(EconomicEvent).all()
    assert len(events) == 1
    assert events[0].actual == "2.6%"
    assert events[0].revised_previous == "2.9%"
    assert events[0].status == "revised"
    assert calendar_status(db).calendar_status == "healthy"


def test_fallback_composite_key_deduplicates_events_without_provider_id():
    db = make_session()
    event_time = datetime.now(timezone.utc) + timedelta(hours=1)
    provider = FakeProvider([_payload(event_time, provider_event_id=None)])

    sync_events(db, start_date=date.today(), end_date=date.today(), provider=provider)
    sync_events(db, start_date=date.today(), end_date=date.today(), provider=provider)

    assert db.query(EconomicEvent).count() == 1
    assert db.query(EconomicEvent).one().fallback_dedupe_key == fallback_dedupe_key("US CPI y/y", "United States", event_time)


def test_medium_impact_window_blocks_and_reports_healthy_calendar(monkeypatch):
    db = make_session()
    event_time = datetime.now(timezone.utc) + timedelta(minutes=15)
    provider = FakeProvider([_payload(event_time, title="US Manufacturing PMI", impact="medium")])
    monkeypatch.setattr(calendar_service, "get_calendar_provider", lambda name=None: provider)
    sync_events(db, start_date=date.today(), end_date=date.today(), provider=provider)

    risk = evaluate_pair_news_risk(db, "EURUSD", now=event_time - timedelta(minutes=15))

    assert risk.calendar_status == "healthy"
    assert risk.blocked is True
    assert risk.block_before_minutes == 20
    assert risk.event is not None
    assert risk.event.impact == "medium"


def test_stale_or_failed_calendar_never_counts_as_safe(monkeypatch):
    db = make_session()
    failing = FakeProvider(error="provider offline")
    monkeypatch.setattr(calendar_service, "get_calendar_provider", lambda name=None: failing)

    assert sync_if_due(db) is False
    status = calendar_status(db)
    risk = evaluate_pair_news_risk(db, "USDJPY")

    assert status.calendar_status == "unavailable"
    assert status.last_error == "provider offline"
    assert risk.blocked is True
    assert risk.calendar_status == "unavailable"


def test_successful_calendar_becomes_stale_after_two_sync_intervals(monkeypatch):
    db = make_session()
    event_time = datetime.now(timezone.utc) + timedelta(hours=3)
    provider = FakeProvider([_payload(event_time)])
    monkeypatch.setattr(calendar_service, "get_calendar_provider", lambda name=None: provider)
    sync_events(db, start_date=date.today(), end_date=date.today(), provider=provider)
    fresh = calendar_status(db)
    stale = calendar_status(db, now=fresh.last_successful_sync_at + timedelta(minutes=31))

    assert fresh.calendar_status == "healthy"
    assert stale.calendar_status == "stale"


def test_calendar_api_contract_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert {
        "/api/calendar/upcoming", "/api/calendar/pair-risk", "/api/calendar/events",
        "/api/calendar/sync", "/api/calendar/status",
    }.issubset(paths)

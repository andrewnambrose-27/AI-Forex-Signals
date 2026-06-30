from datetime import datetime, timedelta, timezone
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.app_setting import AppSetting
from app.models.economic_event import EconomicEvent
from app.services.economic_calendar import currencies_for_pair, evaluate_pair_news_risk, get_calendar_settings, update_calendar_settings


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

    assert risk.blocked is False
    assert risk.event is None

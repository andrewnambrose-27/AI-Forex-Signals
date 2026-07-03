from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.api.routes.ig import _aggregate_candles, _stored_history_warning
from app.models.candle import Candle
from app.services.ig_client import IGClientError, IGConfigurationError


def test_stored_history_warning_is_hidden_when_stored_ig_history_is_complete():
    warning = _stored_history_warning(IGClientError("IG returned HTTP 404"), loaded_count=750, requested_count=750)

    assert warning is None


def test_stored_history_warning_is_hidden_when_stored_ig_history_is_near_complete():
    warning = _stored_history_warning(IGClientError("IG returned HTTP 404"), loaded_count=999, requested_count=1000)

    assert warning is None


def test_stored_history_warning_is_shown_when_stored_ig_history_is_short():
    warning = _stored_history_warning(IGClientError("IG returned HTTP 404"), loaded_count=240, requested_count=750)

    assert warning == "Using stored IG candle history because the latest IG REST request failed: IG returned HTTP 404."


def test_stored_history_warning_is_shown_when_ig_is_not_configured():
    warning = _stored_history_warning(IGConfigurationError(), loaded_count=750, requested_count=750)

    assert warning == "Using stored IG candles because IG is not configured."


def test_aggregate_candles_builds_complete_15_minute_bucket_from_5_minute_candles():
    source = [
        _candle("2026-07-03T12:00:00+00:00", "1.1000", "1.1010", "1.0990", "1.1005", "2"),
        _candle("2026-07-03T12:05:00+00:00", "1.1005", "1.1020", "1.1000", "1.1015", "3"),
        _candle("2026-07-03T12:10:00+00:00", "1.1015", "1.1030", "1.1010", "1.1025", "4"),
    ]

    candles = _aggregate_candles(source, "CS.D.EURUSD.MINI.IP", "MINUTE_15", timedelta(minutes=15))

    assert len(candles) == 1
    assert candles[0].opened_at == datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    assert candles[0].open == Decimal("1.1000")
    assert candles[0].high == Decimal("1.1030")
    assert candles[0].low == Decimal("1.0990")
    assert candles[0].close == Decimal("1.1025")
    assert candles[0].volume == Decimal("9")


def test_aggregate_candles_skips_incomplete_15_minute_bucket():
    source = [
        _candle("2026-07-03T12:00:00+00:00", "1.1000", "1.1010", "1.0990", "1.1005", None),
        _candle("2026-07-03T12:05:00+00:00", "1.1005", "1.1020", "1.1000", "1.1015", None),
    ]

    candles = _aggregate_candles(source, "CS.D.EURUSD.MINI.IP", "MINUTE_15", timedelta(minutes=15))

    assert candles == []


def _candle(opened_at: str, open_: str, high: str, low: str, close: str, volume: str | None) -> Candle:
    return Candle(
        epic="CS.D.EURUSD.MINI.IP",
        symbol="CS.D.EURUSD.MINI.IP",
        timeframe="MINUTE_5",
        resolution="MINUTE_5",
        provider="ig",
        opened_at=datetime.fromisoformat(opened_at),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume) if volume is not None else None,
        raw_data={},
    )

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.routes import multi_timeframe as multi_route
from app.services.multi_timeframe import (
    analyze_multi_timeframe,
    analyze_timeframe_state,
    closed_candles_available_at,
    required_timeframes,
)


def _candles(direction: int, *, timeframe_minutes: int = 5, count: int = 260):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 1.1 if direction >= 0 else 1.3
    result = []
    for index in range(count):
        change = 0.0002 * direction
        close = price + change
        result.append(
            SimpleNamespace(
                opened_at=start + timedelta(minutes=timeframe_minutes * index),
                open=price,
                high=max(price, close) + 0.0003,
                low=min(price, close) - 0.0003,
                close=close,
                is_closed=True,
            )
        )
        price = close
    return result


def test_default_timeframe_relationships_are_complete():
    assert required_timeframes("5m") == ["5m", "15m", "1h"]
    assert required_timeframes("15m") == ["15m", "1h", "4h"]
    assert required_timeframes("1h") == ["1h", "4h", "1d"]
    assert required_timeframes("4h") == ["4h", "1d"]


def test_aligned_states_return_overall_bullish_confirmation():
    analysis = analyze_multi_timeframe(
        {"5m": _candles(1, timeframe_minutes=5), "15m": _candles(1, timeframe_minutes=15), "1h": _candles(1, timeframe_minutes=60)},
        entry_timeframe="5m",
        signal_direction="BUY",
    )

    assert analysis.result == "aligned"
    assert analysis.overall_direction == "bullish"
    assert analysis.score_penalty == 0
    assert analysis.strong_conflict is False
    assert "5m, 15m, and 1h structure are bullish" in analysis.reasons[0]


def test_strong_directional_bias_conflict_filters_opposing_signal():
    analysis = analyze_multi_timeframe(
        {"5m": _candles(-1, timeframe_minutes=5), "15m": _candles(-1, timeframe_minutes=15), "1h": _candles(1, timeframe_minutes=60)},
        entry_timeframe="5m",
        signal_direction="SELL",
    )

    assert analysis.result == "conflicting"
    assert analysis.higher_timeframe_state is not None
    assert analysis.higher_timeframe_state.trend_strength == "strong"
    assert analysis.strong_conflict is True
    assert analysis.score_penalty == 20
    assert "Signal filtered" in analysis.reasons[-1]


def test_open_streaming_candle_cannot_change_timeframe_state():
    candles = _candles(1)
    open_preview = SimpleNamespace(
        opened_at=candles[-1].opened_at + timedelta(minutes=5),
        open=1.0, high=9.0, low=0.1, close=0.1, is_closed=False,
    )

    assert analyze_timeframe_state([*candles, open_preview], timeframe="5m", role="entry") == analyze_timeframe_state(candles, timeframe="5m", role="entry")


def test_higher_timeframe_candle_is_unavailable_until_its_close_time():
    candles = _candles(1, timeframe_minutes=60, count=3)
    first_open = candles[0].opened_at

    assert closed_candles_available_at(candles, "1h", first_open + timedelta(minutes=59)) == []
    assert closed_candles_available_at(candles, "1h", first_open + timedelta(hours=1)) == [candles[0]]
    assert closed_candles_available_at(candles, "1h", first_open + timedelta(hours=1, minutes=59)) == [candles[0]]


def test_analysis_endpoint_uses_short_lived_result_cache(monkeypatch):
    multi_route._analysis_cache.clear()
    calls: list[str] = []
    candles = _candles(1)
    monkeypatch.setattr(multi_route, "_resolve_epic", lambda symbol: "TEST.EPIC")

    def fake_fetch_candles(**kwargs):
        calls.append(kwargs["resolution"])
        return {"candles": candles}

    monkeypatch.setattr(multi_route, "fetch_candles", fake_fetch_candles)
    first = multi_route.get_multi_timeframe_analysis(db=object(), symbol="EURUSD", timeframe="5m")
    second = multi_route.get_multi_timeframe_analysis(db=object(), symbol="EURUSD", timeframe="5m")

    assert first == second
    assert calls == ["5m", "15m", "1h"]

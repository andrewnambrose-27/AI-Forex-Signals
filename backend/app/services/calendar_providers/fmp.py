from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.services.calendar_providers.base import CalendarProviderError, EconomicCalendarProvider, ProviderHealth


class FMPEconomicCalendarProvider(EconomicCalendarProvider):
    name = "fmp"
    endpoint = "https://financialmodelingprep.com/stable/economic-calendar"

    def __init__(self, api_key: str | None, *, timeout_seconds: float = 12.0, client: httpx.Client | None = None) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = timeout_seconds
        self.client = client

    def fetch_events(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        if not self.api_key:
            raise CalendarProviderError("FMP_API_KEY is not configured")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        try:
            if self.client is not None:
                response = self.client.get(
                    self.endpoint,
                    params={"from": start_date.isoformat(), "to": end_date.isoformat()},
                    headers={"apikey": self.api_key},
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(
                        self.endpoint,
                        params={"from": start_date.isoformat(), "to": end_date.isoformat()},
                        headers={"apikey": self.api_key},
                    )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CalendarProviderError(f"FMP economic calendar request failed: {exc}") from exc
        if not isinstance(payload, list):
            raise CalendarProviderError("FMP economic calendar returned an unexpected payload")
        return [item for item in payload if isinstance(item, dict)]

    def normalize_event(self, raw_event: dict[str, Any]) -> Any:
        # Imported lazily so the provider contract remains independent of the
        # persistence/service implementation and future providers can reuse it.
        from app.services.economic_calendar import CalendarEventPayload, classify_event_impact, country_currency

        title = _text(raw_event, "event", "title", "name") or "Untitled economic event"
        country = _text(raw_event, "country", "region")
        currency = (_text(raw_event, "currency", "symbol") or country_currency(country) or "UNK").upper()
        event_time = _parse_datetime(_value(raw_event, "date", "eventTime", "datetime", "time"))
        impact = _normalize_impact(_text(raw_event, "impact", "importance"), title)
        actual = _string_value(raw_event, "actual")
        revised_previous = _string_value(raw_event, "revisedPrevious", "revised_previous", "revision")
        explicit_status = (_text(raw_event, "status") or "").lower()
        status = explicit_status if explicit_status in {"scheduled", "released", "revised", "cancelled"} else "revised" if revised_previous is not None else "released" if actual is not None else "scheduled"
        return CalendarEventPayload(
            provider=self.name,
            provider_event_id=_string_value(raw_event, "id", "eventId", "event_id"),
            title=title,
            country=country,
            currency=currency,
            event_time_utc=event_time,
            impact=impact or classify_event_impact(title),
            actual=actual,
            forecast=_string_value(raw_event, "estimate", "forecast", "consensus"),
            previous=_string_value(raw_event, "previous"),
            revised_previous=revised_previous,
            unit=_string_value(raw_event, "unit"),
            source=_text(raw_event, "source") or "Financial Modeling Prep",
            status=status,
            raw_payload=dict(raw_event),
        )

    def health_check(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(self.name, False, False, "FMP_API_KEY is not configured")
        try:
            utc_today = datetime.now(timezone.utc).date()
            self.fetch_events(utc_today, utc_today)
        except CalendarProviderError as exc:
            return ProviderHealth(self.name, False, True, str(exc))
        return ProviderHealth(self.name, True, True, "FMP economic calendar is reachable")


def _normalize_impact(value: str | None, title: str) -> str:
    if value:
        normalized = value.strip().lower()
        aliases = {"3": "high", "2": "medium", "1": "low", "high": "high", "medium": "medium", "moderate": "medium", "low": "low"}
        if normalized in aliases:
            return aliases[normalized]
    from app.services.economic_calendar import classify_event_impact
    return classify_event_impact(title)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise CalendarProviderError(f"Invalid FMP event date: {value}") from exc
    else:
        raise CalendarProviderError("FMP event is missing its UTC date")
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _value(raw: dict[str, Any], *names: str) -> Any:
    return next((raw[name] for name in names if name in raw), None)


def _text(raw: dict[str, Any], *names: str) -> str | None:
    value = _value(raw, *names)
    return str(value).strip() if value is not None and str(value).strip() else None


def _string_value(raw: dict[str, Any], *names: str) -> str | None:
    value = _value(raw, *names)
    return None if value is None or value == "" else str(value)

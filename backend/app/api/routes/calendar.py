from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSession
from app.schemas.calendar import (
    CalendarEventsRead, CalendarSettingsRead, CalendarSettingsUpdate, CalendarStatusRead,
    CalendarSyncRead, CalendarSyncRequest, PairRiskRead,
)
from app.services.calendar_providers.base import CalendarProviderError
from app.services.economic_calendar import (
    calendar_status, evaluate_pair_news_risk, events_for_currency, get_calendar_provider,
    get_calendar_settings, sync_events, upcoming_events, update_calendar_settings,
)


router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/upcoming", response_model=CalendarEventsRead)
def calendar_upcoming(
    db: DbSession,
    currency: str | None = Query(None, min_length=3, max_length=3),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    currencies = [currency.upper()] if currency else None
    events = upcoming_events(db, currencies=currencies, limit=limit)
    return {"calendar_status": calendar_status(db).calendar_status, "events": events}


@router.get("/pair-risk", response_model=PairRiskRead)
def calendar_pair_risk(symbol: str, db: DbSession) -> PairRiskRead:
    risk = evaluate_pair_news_risk(db, symbol)
    return PairRiskRead(
        pair=risk.pair, currencies=risk.currencies, blocked=risk.blocked, reason=risk.reason,
        block_before_minutes=risk.block_before_minutes, block_after_minutes=risk.block_after_minutes,
        event=risk.event, upcoming_events=risk.upcoming_events, calendar_status=risk.calendar_status,
        last_synced_at=risk.last_synced_at,
    )


@router.get("/events", response_model=CalendarEventsRead)
def calendar_events(
    db: DbSession,
    currency: str = Query(..., min_length=3, max_length=3),
    days: int = Query(7, ge=1, le=90),
) -> dict:
    events = events_for_currency(db, currency, days)
    return {"calendar_status": calendar_status(db).calendar_status, "events": events}


@router.post("/sync", response_model=CalendarSyncRead)
def calendar_sync(payload: CalendarSyncRequest, db: DbSession) -> CalendarSyncRead:
    utc_today = datetime.now(timezone.utc).date()
    start = payload.start_date or utc_today - timedelta(days=1)
    end = payload.end_date or utc_today + timedelta(days=7)
    if end < start:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    provider = get_calendar_provider(str(get_calendar_settings(db)["provider"]))
    try:
        events = sync_events(db, start_date=start, end_date=end, provider=provider)
    except CalendarProviderError as exc:
        raise HTTPException(status_code=503, detail={"message": "Economic calendar sync failed", "provider": provider.name, "error": str(exc)}) from exc
    status = calendar_status(db)
    return CalendarSyncRead(
        provider=provider.name, synced_events=len(events), start_date=start, end_date=end,
        calendar_status=status.calendar_status, last_successful_sync_at=status.last_successful_sync_at,
    )


@router.get("/status", response_model=CalendarStatusRead)
def calendar_provider_status(db: DbSession) -> CalendarStatusRead:
    return CalendarStatusRead(**asdict(calendar_status(db)))


@router.get("/settings", response_model=CalendarSettingsRead)
def calendar_settings(db: DbSession) -> dict:
    return get_calendar_settings(db)


@router.put("/settings", response_model=CalendarSettingsRead)
def update_settings(payload: CalendarSettingsUpdate, db: DbSession) -> dict:
    return update_calendar_settings(db, payload.model_dump(exclude_unset=True))

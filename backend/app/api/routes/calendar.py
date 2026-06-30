from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.calendar import CalendarSettingsRead, CalendarSettingsUpdate, EconomicEventRead, PairRiskRead
from app.services.economic_calendar import (
    evaluate_pair_news_risk,
    get_calendar_settings,
    upcoming_events,
    update_calendar_settings,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/upcoming", response_model=list[EconomicEventRead])
def calendar_upcoming(
    db: DbSession,
    currency: str | None = Query(None, min_length=3, max_length=3),
    limit: int = Query(100, ge=1, le=500),
) -> list:
    currencies = [currency.upper()] if currency else None
    return upcoming_events(db, currencies=currencies, limit=limit)


@router.get("/pair-risk", response_model=PairRiskRead)
def calendar_pair_risk(pair: str, db: DbSession) -> PairRiskRead:
    risk = evaluate_pair_news_risk(db, pair)
    return PairRiskRead(
        pair=risk.pair,
        currencies=risk.currencies,
        blocked=risk.blocked,
        reason=risk.reason,
        block_before_minutes=risk.block_before_minutes,
        block_after_minutes=risk.block_after_minutes,
        event=risk.event,
        upcoming_events=risk.upcoming_events,
    )


@router.get("/settings", response_model=CalendarSettingsRead)
def calendar_settings(db: DbSession) -> dict:
    return get_calendar_settings(db)


@router.put("/settings", response_model=CalendarSettingsRead)
def update_settings(payload: CalendarSettingsUpdate, db: DbSession) -> dict:
    return update_calendar_settings(db, payload.model_dump(exclude_unset=True))

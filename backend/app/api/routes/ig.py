from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.candle import Candle
from app.schemas.candle import CandleRead
from app.services.ig_client import (
    IGClient,
    IGClientError,
    IGConfigurationError,
    parse_ig_candle,
)

router = APIRouter(tags=["ig"])


def get_ig_client() -> IGClient:
    return IGClient()


@router.get("/ig/status")
def ig_status() -> dict[str, Any]:
    client = get_ig_client()
    status = client.status()

    if not status["configured"]:
        return status

    try:
        status["accounts"] = client.get_accounts().get("accounts", [])
        status["authenticated"] = True
    except IGClientError as exc:
        raise _ig_http_exception(exc) from exc

    return status


@router.get("/markets/search")
def search_markets(q: str = Query(..., min_length=2, max_length=80)) -> dict[str, Any]:
    try:
        payload = get_ig_client().search_markets(q)
    except IGClientError as exc:
        raise _ig_http_exception(exc) from exc

    return {
        "query": q,
        "markets": payload.get("markets", []),
    }


@router.get("/candles", response_model=list[CandleRead])
def fetch_candles(
    db: DbSession,
    epic: str = Query(..., min_length=3, max_length=128),
    resolution: str = Query("HOUR", min_length=2, max_length=16),
    limit: int = Query(100, ge=1, le=1000),
) -> list[Candle]:
    normalized_resolution = _normalize_resolution(resolution)

    try:
        payload = get_ig_client().get_historical_prices(epic, normalized_resolution, limit)
    except IGClientError as exc:
        if isinstance(exc, IGConfigurationError):
            return _stored_candles(db, epic, normalized_resolution, limit)
        raise _ig_http_exception(exc) from exc

    candles: list[Candle] = []
    for raw_price in payload.get("prices", []):
        parsed = parse_ig_candle(raw_price, epic, normalized_resolution)
        if parsed is None:
            continue
        candles.append(_upsert_candle(db, parsed))

    db.commit()
    return candles


def _stored_candles(db: DbSession, epic: str, resolution: str, limit: int) -> list[Candle]:
    query = (
        select(Candle)
        .where(Candle.epic == epic, Candle.resolution == resolution, Candle.provider == "ig")
        .order_by(Candle.opened_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


def _upsert_candle(db: DbSession, parsed: dict[str, Any]) -> Candle:
    existing = db.scalar(
        select(Candle).where(
            Candle.epic == parsed["epic"],
            Candle.resolution == parsed["resolution"],
            Candle.opened_at == parsed["opened_at"],
        )
    )

    if existing:
        for key, value in parsed.items():
            setattr(existing, key, value)
        return existing

    candle = Candle(**parsed)
    db.add(candle)
    return candle


def _normalize_resolution(value: str) -> str:
    aliases = {
        "5m": "MINUTE_5",
        "15m": "MINUTE_15",
        "1h": "HOUR",
        "4h": "HOUR_4",
        "1d": "DAY",
    }
    return aliases.get(value.lower(), value.upper())


def _ig_http_exception(exc: IGClientError) -> HTTPException:
    details = {
        "message": str(exc),
        "details": exc.details,
    }
    return HTTPException(status_code=exc.status_code, detail=details)

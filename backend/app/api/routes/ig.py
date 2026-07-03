from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.candle import Candle
from app.schemas.candle import CandleBootstrapRead
from app.services.ig_client import (
    IGClient,
    IGClientError,
    IGConfigurationError,
    parse_ig_candle,
)

router = APIRouter(tags=["ig"])
CANDLE_WARNING_TOLERANCE = 10


def get_ig_client() -> IGClient:
    return IGClient()


@router.get("/ig/status")
def ig_status() -> dict[str, Any]:
    client = get_ig_client()
    status = client.status()
    status["is_demo_environment"] = client.environment == "DEMO"
    status["credentials_present"] = client.is_configured
    status["selected_account_id_exists"] = False

    if not status["configured"]:
        return status

    try:
        accounts = client.get_sanitized_accounts()
        status["authenticated"] = True
    except IGClientError as exc:
        raise _ig_http_exception(exc) from exc

    selected_account_id = status.get("account_id")
    status["accounts"] = accounts
    status["selected_account_id_exists"] = bool(
        selected_account_id and any(account.get("accountId") == selected_account_id for account in accounts)
    )
    return status


@router.get("/ig/accounts")
def ig_accounts() -> dict[str, Any]:
    client = get_ig_client()
    if client.environment != "DEMO":
        raise HTTPException(status_code=400, detail="IG_ENVIRONMENT must be DEMO for this endpoint")

    try:
        accounts = client.get_sanitized_accounts()
    except IGClientError as exc:
        raise _ig_http_exception(exc) from exc

    return {
        "environment": client.environment,
        "accounts": accounts,
    }


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


@router.get("/candles", response_model=CandleBootstrapRead)
def fetch_candles(
    db: DbSession,
    epic: str = Query(..., min_length=3, max_length=128),
    resolution: str = Query("HOUR", min_length=2, max_length=16),
    limit: int | None = Query(None, ge=1, le=1000),
) -> dict[str, Any]:
    normalized_resolution = _normalize_resolution(resolution)
    requested_count = limit or _default_limit_for_resolution(normalized_resolution)

    try:
        payload = get_ig_client().get_historical_prices(epic, normalized_resolution, requested_count)
    except IGClientError as exc:
        candles, dropped_incomplete = _drop_incomplete_current_candle(
            _stored_candles(db, epic, normalized_resolution, requested_count),
            normalized_resolution,
        )
        if candles and not _has_recent_candle(candles, normalized_resolution):
            candles = []
            dropped_incomplete = False
        if not candles:
            candles, dropped_incomplete = _drop_incomplete_current_candle(
                _derived_stored_candles(db, epic, normalized_resolution, requested_count),
                normalized_resolution,
            )
            if candles and not _has_recent_candle(candles, normalized_resolution):
                candles = []
                dropped_incomplete = False
        if candles:
            warning = _stored_history_warning(exc, len(candles), requested_count)
            return _candle_response(
                epic=epic,
                resolution=normalized_resolution,
                requested_count=requested_count,
                candles=candles,
                warning=warning,
                dropped_incomplete_current_candle=dropped_incomplete,
            )
        raise _ig_http_exception(exc) from exc

    candles: list[Candle] = []
    for raw_price in payload.get("prices", []):
        parsed = parse_ig_candle(raw_price, epic, normalized_resolution)
        if parsed is None:
            continue
        candles.append(_upsert_candle(db, parsed))

    db.commit()
    candles = sorted(candles, key=lambda candle: candle.opened_at)
    candles, dropped_incomplete = _drop_incomplete_current_candle(candles, normalized_resolution)
    warning = None
    if len(candles) + CANDLE_WARNING_TOLERANCE < requested_count:
        warning = f"IG returned {len(candles)} closed candles for {normalized_resolution}, fewer than the {requested_count} requested."
    return _candle_response(
        epic=epic,
        resolution=normalized_resolution,
        requested_count=requested_count,
        candles=candles,
        warning=warning,
        dropped_incomplete_current_candle=dropped_incomplete,
    )


def _stored_candles(db: DbSession, epic: str, resolution: str, limit: int) -> list[Candle]:
    query = (
        select(Candle)
        .where(Candle.epic == epic, Candle.resolution == resolution, Candle.provider == "ig")
        .order_by(Candle.opened_at.desc())
        .limit(limit)
    )
    return sorted(db.scalars(query), key=lambda candle: candle.opened_at)


def _derived_stored_candles(db: DbSession, epic: str, resolution: str, limit: int) -> list[Candle]:
    if resolution != "MINUTE_15":
        return []

    source_candles = _stored_candles(db, epic, "MINUTE_5", limit * 3)
    return _aggregate_candles(source_candles, epic, resolution, timedelta(minutes=15))


def _aggregate_candles(source_candles: list[Candle], epic: str, resolution: str, duration: timedelta) -> list[Candle]:
    buckets: dict[datetime, list[Candle]] = {}
    source_duration = _resolution_duration("MINUTE_5")
    if source_duration is None:
        return []

    for candle in source_candles:
        opened_at = candle.opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        bucket_start = _floor_datetime(opened_at, duration)
        buckets.setdefault(bucket_start, []).append(candle)

    aggregated: list[Candle] = []
    expected_count = int(duration.total_seconds() / source_duration.total_seconds())
    for opened_at in sorted(buckets):
        bucket = sorted(buckets[opened_at], key=lambda candle: candle.opened_at)
        if len(bucket) < expected_count:
            continue
        volume = _sum_optional_decimals(candle.volume for candle in bucket)
        aggregated.append(
            Candle(
                epic=epic,
                symbol=epic,
                timeframe=resolution,
                resolution=resolution,
                provider="ig",
                opened_at=opened_at,
                open=bucket[0].open,
                high=max(candle.high for candle in bucket),
                low=min(candle.low for candle in bucket),
                close=bucket[-1].close,
                volume=volume,
                raw_data={"source": "stored_ig_aggregation", "source_resolution": "MINUTE_5"},
            )
        )
    return aggregated


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


def _default_limit_for_resolution(resolution: str) -> int:
    defaults = {
        "MINUTE_5": 1000,
        "MINUTE_15": 1000,
        "HOUR": 750,
        "HOUR_4": 500,
        "DAY": 400,
    }
    return defaults.get(resolution, 750)


def _drop_incomplete_current_candle(candles: list[Candle], resolution: str) -> tuple[list[Candle], bool]:
    if not candles:
        return candles, False

    duration = _resolution_duration(resolution)
    if duration is None:
        return candles, False

    latest = candles[-1]
    opened_at = latest.opened_at
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)

    if opened_at + duration > datetime.now(timezone.utc):
        return candles[:-1], True
    return candles, False


def _has_recent_candle(candles: list[Candle], resolution: str) -> bool:
    if not candles:
        return False

    duration = _resolution_duration(resolution)
    if duration is None:
        return True

    latest_opened_at = candles[-1].opened_at
    if latest_opened_at.tzinfo is None:
        latest_opened_at = latest_opened_at.replace(tzinfo=timezone.utc)
    return latest_opened_at + (duration * 3) >= datetime.now(timezone.utc)


def _resolution_duration(resolution: str) -> timedelta | None:
    durations = {
        "MINUTE_5": timedelta(minutes=5),
        "MINUTE_15": timedelta(minutes=15),
        "HOUR": timedelta(hours=1),
        "HOUR_4": timedelta(hours=4),
        "DAY": timedelta(days=1),
    }
    return durations.get(resolution)


def _floor_datetime(value: datetime, duration: timedelta) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    seconds = int((value - epoch).total_seconds())
    bucket_seconds = int(duration.total_seconds())
    return epoch + timedelta(seconds=seconds - (seconds % bucket_seconds))


def _sum_optional_decimals(values: Any) -> Decimal | None:
    total: Decimal | None = None
    for value in values:
        if value is None:
            continue
        total = value if total is None else total + value
    return total


def _stored_history_warning(exc: IGClientError, loaded_count: int, requested_count: int) -> str | None:
    if isinstance(exc, IGConfigurationError):
        return "Using stored IG candles because IG is not configured."
    if loaded_count + CANDLE_WARNING_TOLERANCE >= requested_count:
        return None
    return f"Using stored IG candle history because the latest IG REST request failed: {str(exc)}."


def _candle_response(
    *,
    epic: str,
    resolution: str,
    requested_count: int,
    candles: list[Candle],
    warning: str | None,
    dropped_incomplete_current_candle: bool = False,
) -> dict[str, Any]:
    return {
        "epic": epic,
        "resolution": resolution,
        "requested_count": requested_count,
        "loaded_count": len(candles),
        "candles": candles,
        "warning": warning,
        "dropped_incomplete_current_candle": dropped_incomplete_current_candle,
    }


def _ig_http_exception(exc: IGClientError) -> HTTPException:
    details = {
        "message": str(exc),
        "details": exc.details,
    }
    return HTTPException(status_code=exc.status_code, detail=details)

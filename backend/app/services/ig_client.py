from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings


class IGClientError(Exception):
    status_code = 502
    message = "IG Markets request failed"

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        super().__init__(message or self.message)
        self.details = details


class IGCredentialsError(IGClientError):
    status_code = 401
    message = "Invalid or missing IG credentials"


class IGSessionExpiredError(IGClientError):
    status_code = 401
    message = "IG session expired"


class IGRateLimitError(IGClientError):
    status_code = 429
    message = "IG rate limit reached"


class IGConfigurationError(IGClientError):
    status_code = 500
    message = "IG connector is not configured"


class IGRequestRejectedError(IGClientError):
    status_code = 502
    message = "IG rejected the request"


@dataclass
class IGSession:
    cst: str
    security_token: str
    account_id: str | None = None
    lightstreamer_endpoint: str | None = None


class IGClient:
    demo_base_url = "https://demo-api.ig.com/gateway/deal"
    live_base_url = "https://api.ig.com/gateway/deal"
    price_request_tolerance = 10
    historical_allowance_cooldown = timedelta(minutes=30)
    _shared_session: IGSession | None = None
    _historical_allowance_blocked_until: datetime | None = None

    def __init__(self) -> None:
        self.settings = get_settings()
        environment = self.settings.ig_environment.upper()
        self.environment = "LIVE" if environment == "LIVE" else "DEMO"
        self.base_url = self.live_base_url if self.environment == "LIVE" else self.demo_base_url

    @property
    def is_configured(self) -> bool:
        return all([self.settings.ig_api_key, self.settings.ig_username, self.settings.ig_password])

    def status(self) -> dict[str, Any]:
        return {
            "provider": "IG Markets",
            "environment": self.environment,
            "base_url": self.base_url,
            "configured": self.is_configured,
            "authenticated": self._shared_session is not None,
            "account_id": self._shared_session.account_id if self._shared_session else self.settings.ig_account_id,
            "trade_placement_enabled": False,
        }

    def get_accounts(self) -> dict[str, Any]:
        return self._request("GET", "/accounts", version="1")

    def get_streaming_session(self) -> IGSession:
        return self._shared_session or self._login()

    def get_sanitized_accounts(self) -> list[dict[str, Any]]:
        payload = self.get_accounts()
        return [sanitize_ig_account(account) for account in payload.get("accounts", [])]

    def search_markets(self, query: str) -> dict[str, Any]:
        return self._request("GET", "/markets", params={"searchTerm": query}, version="1")

    def get_historical_prices(self, epic: str, resolution: str, limit: int) -> dict[str, Any]:
        self._raise_if_historical_allowance_blocked()
        bounded_limit = max(1, min(limit, 1000))
        start_at, end_at = _historical_range(resolution, bounded_limit)
        attempts = [
            {
                "label": "v3 query max",
                "path": f"/prices/{epic}",
                "params": {"resolution": resolution, "max": bounded_limit},
                "version": "3",
            },
            {
                "label": "v2 count path",
                "path": f"/prices/{epic}/{resolution}/{bounded_limit}",
                "params": None,
                "version": "2",
            },
            {
                "label": "v2 date range path",
                "path": f"/prices/{epic}/{resolution}/{_format_ig_range_datetime(start_at)}/{_format_ig_range_datetime(end_at)}",
                "params": None,
                "version": "2",
            },
            {
                "label": "v2 query numPoints",
                "path": f"/prices/{epic}",
                "params": {"resolution": resolution, "numPoints": bounded_limit},
                "version": "2",
            },
            {
                "label": "v2 query max",
                "path": f"/prices/{epic}",
                "params": {"resolution": resolution, "max": bounded_limit},
                "version": "2",
            },
        ]

        best_payload: dict[str, Any] | None = None
        last_error: IGClientError | None = None
        attempt_errors: list[dict[str, Any]] = []
        for attempt in attempts:
            try:
                payload = self._request(
                    "GET",
                    attempt["path"],
                    params=attempt["params"],
                    version=attempt["version"],
                )
            except IGClientError as exc:
                last_error = exc
                attempt_errors.append(
                    {
                        "attempt": attempt["label"],
                        "path": attempt["path"],
                        "params": attempt["params"],
                        "version": attempt["version"],
                        "message": str(exc),
                        "details": exc.details,
                    }
                )
                if _is_historical_allowance_error(exc):
                    blocked_until = datetime.now(timezone.utc) + self.historical_allowance_cooldown
                    IGClient._historical_allowance_blocked_until = blocked_until
                    raise IGRateLimitError(
                        "IG historical data allowance exceeded",
                        details={
                            "attempts": attempt_errors,
                            "errorCode": _ig_error_code(exc),
                            "retryAfterSeconds": int(self.historical_allowance_cooldown.total_seconds()),
                            "blockedUntil": blocked_until.isoformat(),
                        },
                    ) from exc
                continue

            if _price_count(payload) + self.price_request_tolerance >= bounded_limit:
                return payload
            if best_payload is None or _price_count(payload) > _price_count(best_payload):
                best_payload = payload

        if best_payload is not None and _price_count(best_payload) > 0 and last_error is None:
            return best_payload
        if last_error is not None:
            raise IGClientError("IG historical price request failed", details={"attempts": attempt_errors})
        return best_payload or {"prices": []}

    def _raise_if_historical_allowance_blocked(self) -> None:
        blocked_until = self._historical_allowance_blocked_until
        now = datetime.now(timezone.utc)
        if blocked_until is None or blocked_until <= now:
            if blocked_until is not None:
                IGClient._historical_allowance_blocked_until = None
            return

        retry_after_seconds = max(1, int((blocked_until - now).total_seconds()))
        raise IGRateLimitError(
            "IG historical data allowance cooldown active",
            details={
                "errorCode": "error.public-api.exceeded-account-historical-data-allowance",
                "retryAfterSeconds": retry_after_seconds,
                "blockedUntil": blocked_until.isoformat(),
            },
        )

    def _login(self) -> IGSession:
        if not self.is_configured:
            raise IGConfigurationError("Set IG_API_KEY, IG_USERNAME, and IG_PASSWORD before calling IG Markets")

        headers = self._base_headers(version="2")
        payload = {
            "identifier": self.settings.ig_username,
            "password": self.settings.ig_password,
        }

        with httpx.Client(base_url=self.base_url, timeout=20) as client:
            response = client.post("/session", headers=headers, json=payload)

        if response.status_code in {400, 401, 403}:
            raise IGCredentialsError("IG rejected the configured credentials", details=self._safe_json(response))

        self._raise_for_response(response)

        cst = response.headers.get("CST")
        security_token = response.headers.get("X-SECURITY-TOKEN")
        if not cst or not security_token:
            raise IGCredentialsError("IG login did not return session tokens", details=self._safe_json(response))

        payload = self._safe_json(response)
        account_id = self.settings.ig_account_id or payload.get("currentAccountId")
        IGClient._shared_session = IGSession(
            cst=cst,
            security_token=security_token,
            account_id=account_id,
            lightstreamer_endpoint=payload.get("lightstreamerEndpoint"),
        )
        return IGClient._shared_session

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        version: str = "1",
        retry_on_expired_session: bool = True,
    ) -> dict[str, Any]:
        session = self._shared_session or self._login()
        headers = self._session_headers(session, version=version)

        with httpx.Client(base_url=self.base_url, timeout=30) as client:
            response = client.request(method, path, headers=headers, params=params)

        if response.status_code == 401 and retry_on_expired_session:
            IGClient._shared_session = None
            return self._request(method, path, params=params, version=version, retry_on_expired_session=False)

        self._raise_for_response(response)
        return self._safe_json(response)

    def _base_headers(self, *, version: str) -> dict[str, str]:
        if not self.settings.ig_api_key:
            raise IGConfigurationError("Set IG_API_KEY before calling IG Markets")

        return {
            "Accept": "application/json; charset=UTF-8",
            "Content-Type": "application/json; charset=UTF-8",
            "X-IG-API-KEY": self.settings.ig_api_key,
            "Version": version,
        }

    def _session_headers(self, session: IGSession, *, version: str) -> dict[str, str]:
        headers = self._base_headers(version=version)
        headers["CST"] = session.cst
        headers["X-SECURITY-TOKEN"] = session.security_token
        if session.account_id:
            headers["IG-ACCOUNT-ID"] = session.account_id
        return headers

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise IGRateLimitError(details=self._safe_json(response))
        if response.status_code == 401:
            raise IGSessionExpiredError("IG session expired or was rejected", details=self._safe_json(response))
        if response.status_code in {400, 403}:
            raise IGRequestRejectedError(f"IG rejected the request with HTTP {response.status_code}", details=self._safe_json(response))
        if response.is_error:
            raise IGClientError(f"IG returned HTTP {response.status_code}", details=self._safe_json(response))

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {"body": response.text}
        return payload if isinstance(payload, dict) else {"data": payload}


def parse_ig_candle(price: dict[str, Any], epic: str, resolution: str) -> dict[str, Any] | None:
    opened_at = _parse_ig_timestamp(price.get("snapshotTimeUTC") or price.get("snapshotTime"))
    open_price = _midpoint(price.get("openPrice") or {})
    high_price = _midpoint(price.get("highPrice") or {})
    low_price = _midpoint(price.get("lowPrice") or {})
    close_price = _midpoint(price.get("closePrice") or {})

    if not all([opened_at, open_price, high_price, low_price, close_price]):
        return None

    return {
        "epic": epic,
        "symbol": epic,
        "timeframe": resolution,
        "resolution": resolution,
        "provider": "ig",
        "opened_at": opened_at,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": _decimal_or_none(price.get("lastTradedVolume")),
        "raw_data": price,
    }


def _midpoint(value: dict[str, Any]) -> Decimal | None:
    bid = _decimal_or_none(value.get("bid"))
    ask = _decimal_or_none(value.get("ask"))
    last = _decimal_or_none(value.get("lastTraded"))

    if bid is not None and ask is not None:
        return (bid + ask) / Decimal("2")
    return bid or ask or last


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _price_count(payload: dict[str, Any]) -> int:
    prices = payload.get("prices")
    return len(prices) if isinstance(prices, list) else 0


def _is_historical_allowance_error(exc: IGClientError) -> bool:
    return _ig_error_code(exc) == "error.public-api.exceeded-account-historical-data-allowance"


def _ig_error_code(exc: IGClientError) -> str | None:
    details = exc.details
    return details.get("errorCode") if isinstance(details, dict) else None


def _historical_range(resolution: str, limit: int) -> tuple[datetime, datetime]:
    duration = _resolution_duration(resolution) or timedelta(hours=1)
    end_at = datetime.now(timezone.utc)
    return end_at - (duration * (limit + 10)), end_at


def _resolution_duration(resolution: str) -> timedelta | None:
    durations = {
        "MINUTE_5": timedelta(minutes=5),
        "MINUTE_15": timedelta(minutes=15),
        "HOUR": timedelta(hours=1),
        "HOUR_4": timedelta(hours=4),
        "DAY": timedelta(days=1),
    }
    return durations.get(resolution)


def _format_ig_range_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_ig_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    for date_format in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(normalized, date_format)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def sanitize_ig_account(account: dict[str, Any]) -> dict[str, Any]:
    preferred = (
        account.get("preferred")
        if "preferred" in account
        else account.get("default")
        if "default" in account
        else account.get("isDefault")
        if "isDefault" in account
        else account.get("selected")
    )

    return {
        "accountName": account.get("accountName") or account.get("accountAlias"),
        "accountType": account.get("accountType"),
        "accountId": account.get("accountId"),
        "preferred": bool(preferred) if preferred is not None else None,
    }

from dataclasses import dataclass
from datetime import datetime, timezone
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


@dataclass
class IGSession:
    cst: str
    security_token: str
    account_id: str | None = None


class IGClient:
    demo_base_url = "https://demo-api.ig.com/gateway/deal"
    live_base_url = "https://api.ig.com/gateway/deal"

    def __init__(self) -> None:
        self.settings = get_settings()
        environment = self.settings.ig_environment.upper()
        self.environment = "LIVE" if environment == "LIVE" else "DEMO"
        self.base_url = self.live_base_url if self.environment == "LIVE" else self.demo_base_url
        self._session: IGSession | None = None

    @property
    def is_configured(self) -> bool:
        return all([self.settings.ig_api_key, self.settings.ig_username, self.settings.ig_password])

    def status(self) -> dict[str, Any]:
        return {
            "provider": "IG Markets",
            "environment": self.environment,
            "base_url": self.base_url,
            "configured": self.is_configured,
            "authenticated": self._session is not None,
            "account_id": self._session.account_id if self._session else self.settings.ig_account_id,
            "trade_placement_enabled": False,
        }

    def get_accounts(self) -> dict[str, Any]:
        return self._request("GET", "/accounts", version="1")

    def get_sanitized_accounts(self) -> list[dict[str, Any]]:
        payload = self.get_accounts()
        return [sanitize_ig_account(account) for account in payload.get("accounts", [])]

    def search_markets(self, query: str) -> dict[str, Any]:
        return self._request("GET", "/markets", params={"searchTerm": query}, version="1")

    def get_historical_prices(self, epic: str, resolution: str, limit: int) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 1000))
        return self._request(
            "GET",
            f"/prices/{epic}",
            params={"resolution": resolution, "numPoints": bounded_limit},
            version="3",
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

        account_id = self.settings.ig_account_id or self._safe_json(response).get("currentAccountId")
        self._session = IGSession(cst=cst, security_token=security_token, account_id=account_id)
        return self._session

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        version: str = "1",
        retry_on_expired_session: bool = True,
    ) -> dict[str, Any]:
        session = self._session or self._login()
        headers = self._session_headers(session, version=version)

        with httpx.Client(base_url=self.base_url, timeout=30) as client:
            response = client.request(method, path, headers=headers, params=params)

        if response.status_code == 401 and retry_on_expired_session:
            self._session = None
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
            raise IGSessionExpiredError(details=self._safe_json(response))
        if response.status_code in {400, 403}:
            raise IGCredentialsError(details=self._safe_json(response))
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

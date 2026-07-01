from typing import Any

from app.services.ig_client import IGClient, sanitize_ig_account


class RecordingIGClient(IGClient):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        version: str = "1",
        retry_on_expired_session: bool = True,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "version": version,
                "retry_on_expired_session": retry_on_expired_session,
            }
        )
        return {"prices": []}


def test_sanitize_ig_account_only_returns_safe_account_fields():
    account = {
        "accountName": "Demo CFD",
        "accountType": "CFD",
        "accountId": "ABC123",
        "preferred": True,
        "balance": {"available": 10000},
        "CST": "do-not-return",
        "X-SECURITY-TOKEN": "do-not-return",
        "apiKey": "do-not-return",
    }

    assert sanitize_ig_account(account) == {
        "accountName": "Demo CFD",
        "accountType": "CFD",
        "accountId": "ABC123",
        "preferred": True,
    }


def test_sanitize_ig_account_supports_default_flag_alias():
    account = {
        "accountAlias": "Spread bet demo",
        "accountType": "SPREADBET",
        "accountId": "XYZ789",
        "isDefault": True,
    }

    assert sanitize_ig_account(account) == {
        "accountName": "Spread bet demo",
        "accountType": "SPREADBET",
        "accountId": "XYZ789",
        "preferred": True,
    }


def test_historical_prices_uses_explicit_ig_count_path():
    client = RecordingIGClient()

    assert client.get_historical_prices("CS.D.EURUSD.CFD.IP", "HOUR", 300) == {"prices": []}
    assert client.calls == [
        {
            "method": "GET",
            "path": "/prices/CS.D.EURUSD.CFD.IP/HOUR/300",
            "params": None,
            "version": "2",
            "retry_on_expired_session": True,
        }
    ]

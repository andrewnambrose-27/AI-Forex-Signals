from typing import Any

from app.services.ig_client import IGClient, IGClientError, sanitize_ig_account


class RecordingIGClient(IGClient):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any] | Exception] = [{"prices": []}]

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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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


def test_historical_prices_uses_explicit_count_path_first():
    client = RecordingIGClient()
    payload = {"prices": [{} for _ in range(291)]}
    client.responses = [payload]

    assert client.get_historical_prices("CS.D.EURUSD.CFD.IP", "HOUR", 300) == payload
    assert client.calls == [
        {
            "method": "GET",
            "path": "/prices/CS.D.EURUSD.CFD.IP/HOUR/300",
            "params": None,
            "version": "2",
            "retry_on_expired_session": True,
        }
    ]


def test_historical_prices_accepts_near_complete_count_payload_without_extra_fallbacks():
    client = RecordingIGClient()
    payload = {"prices": [{} for _ in range(999)]}
    client.responses = [payload]

    assert client.get_historical_prices("CS.D.EURUSD.CFD.IP", "MINUTE_5", 1000) == payload
    assert len(client.calls) == 1


def test_historical_prices_falls_back_to_numpoints_query_when_count_path_returns_too_few():
    client = RecordingIGClient()
    full_payload = {"prices": [{} for _ in range(300)]}
    client.responses = [
        {"prices": [{} for _ in range(9)]},
        full_payload,
    ]

    assert client.get_historical_prices("CS.D.EURUSD.CFD.IP", "HOUR", 300) == full_payload
    assert client.calls == [
        {
            "method": "GET",
            "path": "/prices/CS.D.EURUSD.CFD.IP/HOUR/300",
            "params": None,
            "version": "2",
            "retry_on_expired_session": True,
        },
        {
            "method": "GET",
            "path": "/prices/CS.D.EURUSD.CFD.IP",
            "params": {"resolution": "HOUR", "numPoints": 300},
            "version": "2",
            "retry_on_expired_session": True,
        },
    ]


def test_historical_prices_raises_rejected_attempt_when_only_short_payloads_succeeded():
    client = RecordingIGClient()
    short_payload = {"prices": [{} for _ in range(9)]}
    client.responses = [
        short_payload,
        IGClientError("numPoints path failed"),
    ]

    try:
        client.get_historical_prices("CS.D.EURUSD.CFD.IP", "HOUR", 300)
    except IGClientError as exc:
        assert str(exc) == "numPoints path failed"
    else:
        raise AssertionError("Expected a rejected historical price request")

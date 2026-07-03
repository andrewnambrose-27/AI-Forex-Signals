from typing import Any

from app.services.ig_client import IGClient, IGClientError, IGRateLimitError, IGRequestRejectedError, sanitize_ig_account


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


def test_historical_prices_uses_v3_query_first():
    client = RecordingIGClient()
    payload = {"prices": [{} for _ in range(291)]}
    client.responses = [payload]

    assert client.get_historical_prices("CS.D.EURUSD.CFD.IP", "HOUR", 300) == payload
    assert client.calls == [
        {
            "method": "GET",
            "path": "/prices/CS.D.EURUSD.CFD.IP",
            "params": {"resolution": "HOUR", "max": 300},
            "version": "3",
            "retry_on_expired_session": True,
        }
    ]


def test_historical_prices_accepts_near_complete_v3_payload_without_extra_fallbacks():
    client = RecordingIGClient()
    payload = {"prices": [{} for _ in range(999)]}
    client.responses = [payload]

    assert client.get_historical_prices("CS.D.EURUSD.CFD.IP", "MINUTE_5", 1000) == payload
    assert len(client.calls) == 1


def test_historical_prices_falls_back_to_count_path_when_v3_returns_too_few():
    client = RecordingIGClient()
    full_payload = {"prices": [{} for _ in range(300)]}
    client.responses = [
        {"prices": [{} for _ in range(9)]},
        full_payload,
    ]

    assert client.get_historical_prices("CS.D.EURUSD.CFD.IP", "HOUR", 300) == full_payload
    assert client.calls[0] == {
        "method": "GET",
        "path": "/prices/CS.D.EURUSD.CFD.IP",
        "params": {"resolution": "HOUR", "max": 300},
        "version": "3",
        "retry_on_expired_session": True,
    }
    assert client.calls[1] == {
        "method": "GET",
        "path": "/prices/CS.D.EURUSD.CFD.IP/HOUR/300",
        "params": None,
        "version": "2",
        "retry_on_expired_session": True,
    }


def test_historical_prices_raises_rejected_attempt_when_only_short_payloads_succeeded():
    client = RecordingIGClient()
    short_payload = {"prices": [{} for _ in range(9)]}
    client.responses = [
        short_payload,
        IGClientError("count path failed"),
        IGClientError("date range path failed"),
        IGClientError("numPoints path failed"),
        IGClientError("max path failed"),
    ]

    try:
        client.get_historical_prices("CS.D.EURUSD.CFD.IP", "HOUR", 300)
    except IGClientError as exc:
        assert str(exc) == "IG historical price request failed"
        assert [attempt["attempt"] for attempt in exc.details["attempts"]] == [
            "v2 count path",
            "v2 date range path",
            "v2 query numPoints",
            "v2 query max",
        ]
    else:
        raise AssertionError("Expected a rejected historical price request")


def test_historical_prices_tries_v2_max_query_after_numpoints_rejection():
    client = RecordingIGClient()
    full_payload = {"prices": [{} for _ in range(300)]}
    client.responses = [
        {"prices": [{} for _ in range(9)]},
        IGClientError("count path failed"),
        IGClientError("date range path failed"),
        IGClientError("numPoints path failed"),
        full_payload,
    ]

    assert client.get_historical_prices("CS.D.EURUSD.CFD.IP", "MINUTE_15", 300) == full_payload
    assert client.calls[-1] == {
        "method": "GET",
        "path": "/prices/CS.D.EURUSD.CFD.IP",
        "params": {"resolution": "MINUTE_15", "max": 300},
        "version": "2",
        "retry_on_expired_session": True,
    }


def test_historical_prices_stops_after_historical_allowance_error():
    client = RecordingIGClient()
    client.responses = [
        IGRequestRejectedError(
            "IG rejected the request with HTTP 403",
            details={"errorCode": "error.public-api.exceeded-account-historical-data-allowance"},
        ),
        {"prices": [{} for _ in range(300)]},
    ]

    try:
        client.get_historical_prices("CS.D.EURUSD.CFD.IP", "HOUR", 300)
    except IGRateLimitError as exc:
        assert str(exc) == "IG historical data allowance exceeded"
        assert exc.details["errorCode"] == "error.public-api.exceeded-account-historical-data-allowance"
        assert len(client.calls) == 1
    else:
        raise AssertionError("Expected historical data allowance error")

from app.services.ig_client import sanitize_ig_account


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

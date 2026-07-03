from app.api.routes.ig import _stored_history_warning
from app.services.ig_client import IGClientError, IGConfigurationError


def test_stored_history_warning_is_hidden_when_stored_ig_history_is_complete():
    warning = _stored_history_warning(IGClientError("IG returned HTTP 404"), loaded_count=750, requested_count=750)

    assert warning is None


def test_stored_history_warning_is_hidden_when_stored_ig_history_is_near_complete():
    warning = _stored_history_warning(IGClientError("IG returned HTTP 404"), loaded_count=999, requested_count=1000)

    assert warning is None


def test_stored_history_warning_is_shown_when_stored_ig_history_is_short():
    warning = _stored_history_warning(IGClientError("IG returned HTTP 404"), loaded_count=240, requested_count=750)

    assert warning == "Using stored IG candle history because the latest IG REST request failed: IG returned HTTP 404."


def test_stored_history_warning_is_shown_when_ig_is_not_configured():
    warning = _stored_history_warning(IGConfigurationError(), loaded_count=750, requested_count=750)

    assert warning == "Using stored IG candles because IG is not configured."

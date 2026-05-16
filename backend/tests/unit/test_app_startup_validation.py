"""Verify the startup-time check that refuses to boot when connectors are
configured but the token-vault encryption key isn't."""

from __future__ import annotations

import pytest

from app.main import _validate_connector_secrets


class _FakeSettings:
    def __init__(self, *, google_id="", slack_id="", encryption_key=""):
        self.GOOGLE_CLIENT_ID = google_id
        self.SLACK_CLIENT_ID = slack_id
        self.ENCRYPTION_KEY = encryption_key


def test_no_connectors_no_key_is_ok():
    # Dev environment without any connector creds — boots fine.
    _validate_connector_secrets(_FakeSettings())  # no raise


def test_no_connectors_with_key_is_ok():
    _validate_connector_secrets(_FakeSettings(encryption_key="present"))  # no raise


def test_google_enabled_without_key_raises():
    with pytest.raises(RuntimeError) as exc_info:
        _validate_connector_secrets(_FakeSettings(google_id="abc.apps.googleusercontent.com"))
    assert "ENCRYPTION_KEY" in str(exc_info.value)
    assert "GOOGLE_CLIENT_ID" in str(exc_info.value) or "google" in str(exc_info.value).lower()


def test_slack_enabled_without_key_raises():
    with pytest.raises(RuntimeError) as exc_info:
        _validate_connector_secrets(_FakeSettings(slack_id="A0123ABC"))
    assert "ENCRYPTION_KEY" in str(exc_info.value)


def test_both_connectors_enabled_with_key_is_ok():
    _validate_connector_secrets(_FakeSettings(
        google_id="g", slack_id="s", encryption_key="present",
    ))  # no raise

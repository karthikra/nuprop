"""Tests for the M16-M20-specific error classes used by the security and
connector layers."""

from __future__ import annotations

from app.core.errors import (
    ConnectorAuthError,
    ConnectorSyncError,
    OAuthStateError,
    TokenVaultError,
)


def test_token_vault_error_carries_code_and_message():
    err = TokenVaultError(code="not_configured", message="ENCRYPTION_KEY is empty")
    assert err.code == "not_configured"
    assert err.message == "ENCRYPTION_KEY is empty"
    assert str(err) == "ENCRYPTION_KEY is empty"
    assert err.cause is None


def test_token_vault_error_carries_cause():
    cause = ValueError("boom")
    err = TokenVaultError(code="decrypt_failed", message="bad ciphertext", cause=cause)
    assert err.cause is cause


def test_oauth_state_error_carries_code():
    err = OAuthStateError(code="signature_mismatch", message="HMAC mismatch")
    assert err.code == "signature_mismatch"


def test_connector_auth_error_inherits_base():
    err = ConnectorAuthError(code="needs_reauth", message="please reconnect")
    assert isinstance(err, Exception)
    assert err.code == "needs_reauth"


def test_connector_sync_error_inherits_base():
    err = ConnectorSyncError(code="domain_failed", message="gmail fetch failed for foo.com")
    assert isinstance(err, Exception)
    assert err.code == "domain_failed"

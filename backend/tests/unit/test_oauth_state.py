"""Tests for the OAuth `state` token — HMAC-signed, time-limited, replay-protected."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from uuid import uuid4

import pytest

from app.core.errors import OAuthStateError
from app.infrastructure.security.oauth_state import (
    InMemoryNonceStore,
    issue_state,
    verify_state,
)

SECRET = "test-secret-not-for-production"
TTL = 600


def _payload_of(token: str) -> dict:
    """Decode the (unsigned) JSON payload from a token for inspection."""
    body, _sig = token.split(".", 1)
    return json.loads(base64.urlsafe_b64decode(body + "==").decode())


async def test_issue_returns_token_with_provider_and_agency_id():
    agency_id = uuid4()
    token = issue_state(agency_id=agency_id, provider="gmail", secret=SECRET, ttl_seconds=TTL)
    assert "." in token  # body.signature
    payload = _payload_of(token)
    assert payload["provider"] == "gmail"
    assert payload["agency_id"] == str(agency_id)
    assert "nonce" in payload and len(payload["nonce"]) >= 16
    assert payload["exp"] > payload["iat"]


async def test_verify_round_trips_agency_id():
    agency_id = uuid4()
    token = issue_state(agency_id=agency_id, provider="gmail", secret=SECRET, ttl_seconds=TTL)
    store = InMemoryNonceStore()
    out = await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert out == agency_id


async def test_verify_rejects_wrong_provider():
    token = issue_state(agency_id=uuid4(), provider="slack", secret=SECRET, ttl_seconds=TTL)
    store = InMemoryNonceStore()
    with pytest.raises(OAuthStateError) as exc_info:
        await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert exc_info.value.code == "provider_mismatch"


async def test_verify_rejects_tampered_signature():
    token = issue_state(agency_id=uuid4(), provider="gmail", secret=SECRET, ttl_seconds=TTL)
    body, sig = token.split(".", 1)
    tampered = f"{body}.{'A' * len(sig)}"
    store = InMemoryNonceStore()
    with pytest.raises(OAuthStateError) as exc_info:
        await verify_state(token=tampered, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert exc_info.value.code == "signature_mismatch"


async def test_verify_rejects_tampered_body():
    token = issue_state(agency_id=uuid4(), provider="gmail", secret=SECRET, ttl_seconds=TTL)
    body, sig = token.split(".", 1)
    # Flip a byte in the body
    decoded = bytearray(base64.urlsafe_b64decode(body + "=="))
    decoded[0] ^= 0xFF
    bad_body = base64.urlsafe_b64encode(bytes(decoded)).decode().rstrip("=")
    store = InMemoryNonceStore()
    with pytest.raises(OAuthStateError):
        await verify_state(token=f"{bad_body}.{sig}", expected_provider="gmail", secret=SECRET, nonce_store=store)


async def test_verify_rejects_expired_token():
    token = issue_state(agency_id=uuid4(), provider="gmail", secret=SECRET, ttl_seconds=-1)
    store = InMemoryNonceStore()
    with pytest.raises(OAuthStateError) as exc_info:
        await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert exc_info.value.code == "expired"


async def test_verify_rejects_replayed_nonce():
    token = issue_state(agency_id=uuid4(), provider="gmail", secret=SECRET, ttl_seconds=TTL)
    store = InMemoryNonceStore()
    # First use succeeds
    await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    # Second use rejected
    with pytest.raises(OAuthStateError) as exc_info:
        await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert exc_info.value.code == "replayed"


async def test_verify_rejects_malformed_token():
    store = InMemoryNonceStore()
    with pytest.raises(OAuthStateError):
        await verify_state(token="no-dot-here", expected_provider="gmail", secret=SECRET, nonce_store=store)


async def test_verify_emits_log_on_security_event(caplog):
    token = issue_state(agency_id=uuid4(), provider="slack", secret=SECRET, ttl_seconds=TTL)
    store = InMemoryNonceStore()
    with caplog.at_level("WARNING", logger="app.infrastructure.security.oauth_state"):
        with pytest.raises(OAuthStateError):
            await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert any("provider_mismatch" in rec.message or "oauth_state" in rec.message for rec in caplog.records)

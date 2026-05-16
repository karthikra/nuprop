"""Tests for the OAuth `state` token — HMAC-signed, time-limited, replay-protected."""

from __future__ import annotations

import base64
import hashlib
import hmac
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


async def test_verify_rejects_non_numeric_exp():
    """C1: a token with non-numeric exp must raise OAuthStateError(malformed),
    NOT a raw ValueError. Constructed by hand to bypass issue_state."""
    payload = {
        "agency_id": str(uuid4()),
        "provider": "gmail",
        "nonce": "test-nonce-1234",
        "iat": int(time.time()),
        "exp": "not-a-number",
    }
    body_bytes = json.dumps(payload, separators=(",", ":")).encode()
    body_b64 = base64.urlsafe_b64encode(body_bytes).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(SECRET.encode(), body_bytes, hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    token = f"{body_b64}.{sig}"

    store = InMemoryNonceStore()
    with pytest.raises(OAuthStateError) as exc_info:
        await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert exc_info.value.code == "malformed"


async def test_verify_rejects_malformed_agency_id_without_burning_nonce():
    """C2: when agency_id parse fails, the nonce slot must NOT have been
    consumed — proving that the next call (with a properly-formed token
    re-using the same nonce) would still succeed if it weren't already burned.
    The simpler assertion: the store has NOT recorded the nonce."""
    payload = {
        "agency_id": "not-a-uuid",
        "provider": "gmail",
        "nonce": "test-nonce-for-c2",
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }
    body_bytes = json.dumps(payload, separators=(",", ":")).encode()
    body_b64 = base64.urlsafe_b64encode(body_bytes).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(SECRET.encode(), body_bytes, hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    token = f"{body_b64}.{sig}"

    store = InMemoryNonceStore()
    with pytest.raises(OAuthStateError) as exc_info:
        await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert exc_info.value.code == "malformed"
    # And the nonce was NOT consumed
    assert "test-nonce-for-c2" not in store._seen  # noqa: SLF001 — verifying invariant


async def test_verify_rejects_missing_nonce():
    """I1: a token with HMAC-valid payload but no nonce field must raise malformed."""
    payload = {
        "agency_id": str(uuid4()),
        "provider": "gmail",
        # nonce intentionally omitted
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }
    body_bytes = json.dumps(payload, separators=(",", ":")).encode()
    body_b64 = base64.urlsafe_b64encode(body_bytes).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(SECRET.encode(), body_bytes, hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    token = f"{body_b64}.{sig}"

    store = InMemoryNonceStore()
    with pytest.raises(OAuthStateError) as exc_info:
        await verify_state(token=token, expected_provider="gmail", secret=SECRET, nonce_store=store)
    assert exc_info.value.code == "malformed"

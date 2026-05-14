"""Unit tests for app.core.security — password hashing and JWT handling."""

from __future__ import annotations

from datetime import timedelta

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_verifies_against_original():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("the-real-password")
    assert verify_password("not-the-password", hashed) is False


def test_hash_password_is_salted():
    """Two hashes of the same password must differ — random per-hash salt."""
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b
    assert verify_password("same-password", a)
    assert verify_password("same-password", b)


def test_hash_password_does_not_contain_plaintext():
    hashed = hash_password("plaintext-secret")
    assert "plaintext-secret" not in hashed


def test_access_token_roundtrip_preserves_claims():
    token = create_access_token({"sub": "user-123", "agency_id": "agency-456"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["agency_id"] == "agency-456"
    assert "exp" in payload


def test_decode_rejects_garbage_token():
    assert decode_access_token("not-a-jwt-at-all") is None


def test_decode_rejects_tampered_signature():
    token = create_access_token({"sub": "user-1"})
    header, payload, _sig = token.split(".")
    tampered = f"{header}.{payload}.invalidsignature"
    assert decode_access_token(tampered) is None


def test_decode_rejects_expired_token():
    token = create_access_token({"sub": "user-1"}, expires_delta=timedelta(seconds=-1))
    assert decode_access_token(token) is None

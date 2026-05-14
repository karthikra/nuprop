"""Unit tests for app.infrastructure.db.repositories.analytics_repo.compute_fingerprint."""

from __future__ import annotations

from app.infrastructure.db.repositories.analytics_repo import compute_fingerprint


def test_fingerprint_is_deterministic():
    a = compute_fingerprint("1.2.3.4", "Mozilla/5.0")
    b = compute_fingerprint("1.2.3.4", "Mozilla/5.0")
    assert a == b


def test_fingerprint_is_24_chars():
    assert len(compute_fingerprint("1.2.3.4", "some-user-agent")) == 24


def test_different_ip_produces_different_fingerprint():
    assert compute_fingerprint("1.2.3.4", "UA") != compute_fingerprint("5.6.7.8", "UA")


def test_different_user_agent_produces_different_fingerprint():
    assert compute_fingerprint("1.2.3.4", "UA-a") != compute_fingerprint("1.2.3.4", "UA-b")

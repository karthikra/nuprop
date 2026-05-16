# S1 — M16-M20 Backend Hardening (CRITICAL fixes) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 5 CRITICAL security/observability holes in the M16-M20 backend so the existing connector scaffolding is safe to enable in production: fail-loud encryption, signed/single-use OAuth state, module-level logging with narrowed excepts, dependency-injected services, and per-domain email-sync commits with watermarks.

**Architecture:** Five small, testable additions plus a logging + except-narrowing sweep across the M16-M20 backend files. A new `app/infrastructure/security/` package holds the token vault and OAuth state primitives. A `NonceStore` Protocol with in-memory and Redis-backed implementations handles OAuth replay protection. The existing `connector_viewmodel.py` is rewritten to use these primitives and to commit emails per-domain with per-domain watermarks. `clients.py` route handlers are switched to FastAPI `Depends()` for `ContextService`. Startup-time validation refuses to boot if connectors are configured without `ENCRYPTION_KEY`.

**Tech Stack:** FastAPI, async SQLAlchemy, `cryptography` (Fernet — already a dep via `connector_viewmodel.py`), `hmac` + `hashlib` + `base64` (stdlib), `redis.asyncio` (already used by ARQ), `pytest` + `pytest-asyncio` + `httpx.ASGITransport` (existing test harness), `caplog` (pytest built-in).

**Spec:** `docs/superpowers/specs/2026-05-16-s1-backend-hardening-design.md`

**Audit context:** `docs/superpowers/audits/2026-05-16-m16-m20-state-audit.md`

**Baseline (before S1):** 244 backend pytest passing, 131 frontend vitest passing. Frontend untouched throughout S1.

---

## File Structure

**New files:**

- `backend/app/core/errors.py` — `TokenVaultError`, `OAuthStateError`, `ConnectorAuthError`, `ConnectorSyncError`
- `backend/app/infrastructure/security/__init__.py` — empty package marker
- `backend/app/infrastructure/security/token_vault.py` — `TokenVault` class (`encrypt`, `decrypt`, `is_configured`, fail-loud)
- `backend/app/infrastructure/security/oauth_state.py` — `issue_state`, `verify_state`, `NonceStore` Protocol, `InMemoryNonceStore`, `RedisNonceStore`
- `backend/tests/unit/test_errors.py` — exception payload tests
- `backend/tests/unit/test_token_vault.py` — encrypt/decrypt + fail-loud
- `backend/tests/unit/test_oauth_state.py` — issue/verify + tampered + expired + wrong-provider + replayed
- `backend/tests/unit/test_app_startup_validation.py` — `_validate_connector_secrets` fail-loud
- `backend/tests/integration/test_gmail_oauth_csrf.py` — callback rejects bad/expired/replayed state
- `backend/tests/integration/test_slack_oauth_csrf.py` — same for Slack
- `backend/tests/integration/test_email_sync_resumption.py` — per-domain commit + watermark
- `backend/tests/integration/test_clients_context_di.py` — `get_context_service` dependency override works

**Modified files:**

- `backend/app/core/deps.py` — additions: `get_token_vault`, `get_context_service`, `get_nonce_store`
- `backend/app/main.py` — call `_validate_connector_secrets()` at the top of `lifespan()`
- `backend/app/services/context_service.py` — module logger; narrow `enrich_context_with_emails` except (line 227)
- `backend/app/services/context_intelligence.py` — module logger; narrow date-parse excepts (lines 88, 103)
- `backend/app/viewmodels/connector_viewmodel.py` — replace `_encrypt`/`_decrypt` with `TokenVault`; rewrite `sync_emails` for per-domain commit + watermark; integrate OAuth state on `get_auth_url`/`handle_callback` + Slack equivalents; narrow every except; module logger; accept injected `gmail_client`/`slack_client`/`token_vault`/`nonce_store`
- `backend/app/infrastructure/external/gmail_client.py` — module logger; narrow `revoke_token`, `fetch_messages_for_domain`, `get_message` date-parse excepts; validate OAuth response shape
- `backend/app/infrastructure/external/slack_client.py` — module logger
- `backend/app/infrastructure/external/gdrive_client.py` — module logger; narrow export-failure except (line 49)
- `backend/app/infrastructure/external/gcal_client.py` — module logger
- `backend/app/infrastructure/db/repositories/email_index_repo.py` — add `upsert_many(rows: list[EmailIndex]) -> int` (chunked commit)
- `backend/app/views/v1/clients.py` — route handlers take `ctx: ContextService = Depends(get_context_service)`; remove inline `ContextService()` instantiation
- `backend/app/views/v1/connectors.py` — Gmail and Slack callbacks resolve `agency_id` from verified state, take `nonce_store: NonceStore = Depends(get_nonce_store)`

**Total:** 4 new app files, 8 new test files, 11 modified app files. Frontend untouched.

---

## Task 1: Create `app/core/errors.py` — exception classes

**Files:**
- Create: `backend/app/core/errors.py`
- Create: `backend/tests/unit/test_errors.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_errors.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.errors'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/core/errors.py`:

```python
"""M16-M20-specific exception hierarchy. Used by the security layer
(`app.infrastructure.security`) and the connector viewmodel to surface
structured failures that route handlers can pattern-match on.

Every error carries a stable `code` string (machine-parseable) and a
human-readable `message`. Optionally wraps an underlying `cause` exception
so the original traceback is preserved for logging."""

from __future__ import annotations


class _StructuredError(Exception):
    """Base for S1 error classes. Carries code + message + optional cause."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause = cause


class TokenVaultError(_StructuredError):
    """Raised when token encryption / decryption fails or is not configured."""


class OAuthStateError(_StructuredError):
    """Raised when OAuth `state` verification fails (signature, expiry,
    provider mismatch, or replay)."""


class ConnectorAuthError(_StructuredError):
    """Raised when a connector's stored credentials are invalid or expired
    and the user must re-authorize."""


class ConnectorSyncError(_StructuredError):
    """Raised when a connector sync operation fails in a way the caller
    should surface (e.g., upstream API outage)."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_errors.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/errors.py backend/tests/unit/test_errors.py
git commit -m "feat(S1): add structured error hierarchy for M16-M20 hardening"
```

---

## Task 2: Create the `infrastructure/security/` package

**Files:**
- Create: `backend/app/infrastructure/security/__init__.py`

- [ ] **Step 1: Create the empty package marker**

Create `backend/app/infrastructure/security/__init__.py` with a single docstring:

```python
"""Security primitives for the M16-M20 surface: token vault (Fernet-backed
encryption with fail-loud semantics) and OAuth state issuance / verification
(HMAC-signed, time-limited, single-use via Redis-backed nonce dedup)."""
```

- [ ] **Step 2: Verify the package imports**

Run: `cd backend && .venv/bin/python -c "import app.infrastructure.security; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/infrastructure/security/__init__.py
git commit -m "feat(S1): scaffold infrastructure/security package"
```

---

## Task 3: `TokenVault` — fail-loud encryption

**Files:**
- Create: `backend/app/infrastructure/security/token_vault.py`
- Create: `backend/tests/unit/test_token_vault.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_token_vault.py`:

```python
"""Tests for the TokenVault — Fernet-backed encryption with fail-loud
semantics. No silent fallback to plaintext."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.errors import TokenVaultError
from app.infrastructure.security.token_vault import TokenVault


def _key() -> str:
    return Fernet.generate_key().decode()


def test_is_configured_true_when_key_present():
    vault = TokenVault(key=_key())
    assert vault.is_configured is True


def test_is_configured_false_when_key_empty():
    vault = TokenVault(key="")
    assert vault.is_configured is False


def test_encrypt_then_decrypt_roundtrips():
    vault = TokenVault(key=_key())
    plaintext = "refresh-token-1ya29Glorem"
    ciphertext = vault.encrypt(plaintext)
    assert ciphertext != plaintext
    assert vault.decrypt(ciphertext) == plaintext


def test_encrypt_without_key_raises_token_vault_error():
    vault = TokenVault(key="")
    with pytest.raises(TokenVaultError) as exc_info:
        vault.encrypt("anything")
    assert exc_info.value.code == "not_configured"


def test_decrypt_without_key_raises_token_vault_error():
    vault = TokenVault(key="")
    with pytest.raises(TokenVaultError) as exc_info:
        vault.decrypt("anything")
    assert exc_info.value.code == "not_configured"


def test_decrypt_of_garbage_raises_token_vault_error():
    vault = TokenVault(key=_key())
    with pytest.raises(TokenVaultError) as exc_info:
        vault.decrypt("not-a-valid-fernet-token")
    assert exc_info.value.code == "decrypt_failed"
    assert exc_info.value.cause is not None


def test_decrypt_with_wrong_key_raises_token_vault_error():
    vault1 = TokenVault(key=_key())
    vault2 = TokenVault(key=_key())
    ciphertext = vault1.encrypt("hello")
    with pytest.raises(TokenVaultError) as exc_info:
        vault2.decrypt(ciphertext)
    assert exc_info.value.code == "decrypt_failed"


def test_encrypt_emits_log_on_failure(caplog):
    vault = TokenVault(key="")
    with caplog.at_level("WARNING", logger="app.infrastructure.security.token_vault"):
        with pytest.raises(TokenVaultError):
            vault.encrypt("anything")
    assert any("not_configured" in rec.message or "ENCRYPTION_KEY" in rec.message for rec in caplog.records)


def test_decrypt_emits_log_on_invalid_token(caplog):
    vault = TokenVault(key=_key())
    with caplog.at_level("WARNING", logger="app.infrastructure.security.token_vault"):
        with pytest.raises(TokenVaultError):
            vault.decrypt("not-valid")
    assert any("decrypt_failed" in rec.message or "InvalidToken" in rec.message for rec in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_token_vault.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/infrastructure/security/token_vault.py`:

```python
"""Fernet-backed token vault for OAuth refresh / access tokens.

Fail-loud semantics:
- `encrypt()` and `decrypt()` raise TokenVaultError("not_configured") if no
  key was provided. There is NO silent fallback to plaintext. The startup
  validator in `app.main` ensures the production process never reaches a
  vault call without configuration.
- `decrypt()` catches `cryptography.fernet.InvalidToken` (corrupted ciphertext
  or wrong key after rotation) and re-raises as TokenVaultError("decrypt_failed").
  Callers map this to a "needs re-auth" surface.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.errors import TokenVaultError

logger = logging.getLogger(__name__)


class TokenVault:
    """Stateless Fernet wrapper. One instance per process is fine (the
    underlying Fernet object is cheap and thread-safe)."""

    def __init__(self, *, key: str) -> None:
        self._key = key or ""
        self._fernet: Fernet | None = (
            Fernet(self._key.encode()) if self._key else None
        )

    @property
    def is_configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        if self._fernet is None:
            logger.warning(
                "token_vault.encrypt called without ENCRYPTION_KEY configured",
                extra={"event": "security.token_vault.not_configured"},
            )
            raise TokenVaultError(
                code="not_configured",
                message="ENCRYPTION_KEY is empty; refusing to encrypt",
            )
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        if self._fernet is None:
            logger.warning(
                "token_vault.decrypt called without ENCRYPTION_KEY configured",
                extra={"event": "security.token_vault.not_configured"},
            )
            raise TokenVaultError(
                code="not_configured",
                message="ENCRYPTION_KEY is empty; refusing to decrypt",
            )
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            logger.warning(
                "token_vault.decrypt rejected an invalid ciphertext (rotated key or corruption)",
                extra={"event": "security.token_vault.decrypt_failed"},
            )
            raise TokenVaultError(
                code="decrypt_failed",
                message="ciphertext could not be decrypted; user must re-authorize",
                cause=exc,
            ) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_token_vault.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/security/token_vault.py backend/tests/unit/test_token_vault.py
git commit -m "feat(S1): TokenVault with fail-loud encrypt/decrypt and InvalidToken handling"
```

---

## Task 4: OAuth state — HMAC issue/verify + NonceStore Protocol

**Files:**
- Create: `backend/app/infrastructure/security/oauth_state.py`
- Create: `backend/tests/unit/test_oauth_state.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_oauth_state.py`:

```python
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
```

The test module needs `pytest-asyncio` mode. Confirm `backend/pyproject.toml` has `asyncio_mode = "auto"` (it does — existing tests use top-level `async def`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_oauth_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.security.oauth_state'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/infrastructure/security/oauth_state.py`:

```python
"""Signed, time-limited, single-use OAuth `state` tokens.

The token is `base64url(JSON payload).base64url(HMAC-SHA256 signature)`.
The payload binds the agency_id and provider name into the OAuth round-trip,
so the callback can verify both that the caller initiated the flow AND that
the response is for the right connector. A random `nonce` is checked against
a NonceStore (Redis in prod, in-memory in dev/test) for replay protection.

The HMAC secret is `JWT_SECRET_KEY` (already a Fly secret) — see Q1 in the
S1 design doc for the rationale of NOT introducing a second secret here.

Reject reasons (OAuthStateError.code):
- `malformed`         — token isn't `body.signature`, or body isn't decodable JSON
- `signature_mismatch`— HMAC doesn't verify
- `expired`           — `exp` is past
- `provider_mismatch` — payload provider != caller's expected provider
- `replayed`          — the nonce was already marked as seen
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Protocol
from uuid import UUID

from app.core.errors import OAuthStateError

logger = logging.getLogger(__name__)


# ── NonceStore abstraction ──────────────────────────────────────────────────


class NonceStore(Protocol):
    """Marks an OAuth state nonce as seen. Returns True if the nonce was
    newly recorded (i.e., this is the first use); False if it was already
    present (replay)."""

    async def mark_seen(self, nonce: str, ttl_seconds: int) -> bool: ...


class InMemoryNonceStore:
    """Process-local nonce store for dev and tests. Bounded by TTL eviction
    on each `mark_seen` call to keep the set small."""

    def __init__(self) -> None:
        self._seen: dict[str, float] = {}

    async def mark_seen(self, nonce: str, ttl_seconds: int) -> bool:
        now = time.time()
        # Evict expired entries opportunistically
        self._seen = {n: exp for n, exp in self._seen.items() if exp > now}
        if nonce in self._seen:
            return False
        self._seen[nonce] = now + ttl_seconds
        return True


class RedisNonceStore:
    """Redis-backed nonce store using `SET key value EX ttl NX`. Returns True
    only when SET actually wrote (i.e., key didn't already exist)."""

    KEY_PREFIX = "oauth_nonce:"

    def __init__(self, redis) -> None:  # noqa: ANN001 — redis.asyncio.Redis
        self._redis = redis

    async def mark_seen(self, nonce: str, ttl_seconds: int) -> bool:
        result = await self._redis.set(
            f"{self.KEY_PREFIX}{nonce}", "", ex=ttl_seconds, nx=True,
        )
        return bool(result)


# ── HMAC encode / verify ─────────────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    # Re-pad to multiple of 4 for base64 decode
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(body_bytes: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), body_bytes, hashlib.sha256).digest()
    return _b64url_encode(sig)


def issue_state(
    *,
    agency_id: UUID,
    provider: str,
    secret: str,
    ttl_seconds: int = 600,
) -> str:
    """Issue a signed state token for the given agency_id + provider.
    `ttl_seconds` is the validity window from `iat`. A 16-byte URL-safe nonce
    is included; the caller must check it against a NonceStore on verify."""
    iat = int(time.time())
    payload = {
        "agency_id": str(agency_id),
        "provider": provider,
        "nonce": secrets.token_urlsafe(16),
        "iat": iat,
        "exp": iat + ttl_seconds,
    }
    body_bytes = json.dumps(payload, separators=(",", ":")).encode()
    body_b64 = _b64url_encode(body_bytes)
    sig = _sign(body_bytes, secret)
    return f"{body_b64}.{sig}"


async def verify_state(
    *,
    token: str,
    expected_provider: str,
    secret: str,
    nonce_store: NonceStore,
) -> UUID:
    """Verify a signed state token. Returns the agency_id on success.
    Raises OAuthStateError with a specific `code` on any failure."""
    # Shape
    if not token or "." not in token:
        logger.warning(
            "oauth_state.verify rejected malformed token",
            extra={"event": "security.oauth_state.malformed"},
        )
        raise OAuthStateError(code="malformed", message="state token is not body.signature")

    body_b64, sig_provided = token.split(".", 1)

    # Decode body
    try:
        body_bytes = _b64url_decode(body_b64)
        payload = json.loads(body_bytes.decode())
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "oauth_state.verify rejected undecodable payload",
            extra={"event": "security.oauth_state.malformed"},
        )
        raise OAuthStateError(
            code="malformed",
            message="state payload is not decodable JSON",
            cause=exc,
        ) from exc

    # Signature (constant-time compare)
    sig_expected = _sign(body_bytes, secret)
    if not hmac.compare_digest(sig_expected, sig_provided):
        logger.warning(
            "oauth_state.verify rejected mismatched signature",
            extra={"event": "security.oauth_state.signature_mismatch"},
        )
        raise OAuthStateError(code="signature_mismatch", message="HMAC verification failed")

    # Expiry
    if int(payload.get("exp", 0)) < int(time.time()):
        logger.warning(
            "oauth_state.verify rejected expired token",
            extra={"event": "security.oauth_state.expired"},
        )
        raise OAuthStateError(code="expired", message="state token has expired")

    # Provider
    if payload.get("provider") != expected_provider:
        logger.warning(
            "oauth_state.verify rejected provider mismatch",
            extra={
                "event": "security.oauth_state.provider_mismatch",
                "expected": expected_provider,
                "got": payload.get("provider"),
            },
        )
        raise OAuthStateError(
            code="provider_mismatch",
            message=f"state was issued for {payload.get('provider')!r}, not {expected_provider!r}",
        )

    # Replay
    nonce = payload.get("nonce", "")
    ttl_remaining = max(60, int(payload.get("exp", 0)) - int(time.time()))
    if not await nonce_store.mark_seen(nonce, ttl_seconds=ttl_remaining):
        logger.warning(
            "oauth_state.verify rejected replayed nonce",
            extra={"event": "security.oauth_state.replayed"},
        )
        raise OAuthStateError(code="replayed", message="state token nonce has already been used")

    return UUID(payload["agency_id"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_oauth_state.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/security/oauth_state.py backend/tests/unit/test_oauth_state.py
git commit -m "feat(S1): OAuth state — HMAC-signed, time-limited, single-use via NonceStore"
```

---

## Task 5: DI helpers — `get_token_vault`, `get_context_service`, `get_nonce_store`

**Files:**
- Modify: `backend/app/core/deps.py`

- [ ] **Step 1: Open `backend/app/core/deps.py` and add the new helpers**

Append the following to `backend/app/core/deps.py` (after the existing `get_current_agency_id` definition):

```python


# ── M16-M20 hardening (S1) — service / vault / nonce-store providers ────────


@lru_cache(maxsize=1)
def get_token_vault() -> "TokenVault":
    """Process singleton. Reads ENCRYPTION_KEY from settings at first call.
    For tests, override via `app.dependency_overrides[get_token_vault]`."""
    from app.core.config import get_settings
    from app.infrastructure.security.token_vault import TokenVault
    return TokenVault(key=get_settings().ENCRYPTION_KEY)


@lru_cache(maxsize=1)
def get_context_service() -> "ContextService":
    """Process singleton. The service is stateless except for its
    AnthropicClient, which is itself process-singleton-safe."""
    from app.services.context_service import ContextService
    return ContextService()


@lru_cache(maxsize=1)
def get_nonce_store() -> "NonceStore":
    """Process singleton. Returns RedisNonceStore in production (REDIS_ENABLED
    and the ARQ Redis pool is alive on app.state), else InMemoryNonceStore for
    dev and tests."""
    from app.core.config import get_settings
    from app.infrastructure.security.oauth_state import InMemoryNonceStore, RedisNonceStore
    settings = get_settings()
    if not settings.REDIS_ENABLED:
        return InMemoryNonceStore()
    # Late import + lazy client construction so the import doesn't crash when
    # Redis isn't available. The client is reused.
    from redis.asyncio import Redis
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return RedisNonceStore(redis)
```

And at the top of `backend/app/core/deps.py`, add `from functools import lru_cache` to the existing imports:

Find the existing import block and modify it. The current top of the file is:

```python
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User
```

Add a `from functools import lru_cache` line after `from __future__ import annotations`:

```python
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `cd backend && .venv/bin/python -c "from app.core.deps import get_token_vault, get_context_service, get_nonce_store; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Run all unit tests to confirm no regression**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/deps.py
git commit -m "feat(S1): DI providers — get_token_vault, get_context_service, get_nonce_store"
```

---

## Task 6: Startup validation — fail-loud if connectors enabled without `ENCRYPTION_KEY`

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/unit/test_app_startup_validation.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_app_startup_validation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_app_startup_validation.py -v`
Expected: FAIL with `ImportError: cannot import name '_validate_connector_secrets' from 'app.main'`.

- [ ] **Step 3: Modify `backend/app/main.py`**

Add the validation function above the `lifespan` definition. Find this block in `backend/app/main.py`:

```python
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
```

And replace it with:

```python
settings = get_settings()


def _validate_connector_secrets(s) -> None:  # noqa: ANN001 — accepts Settings or test double
    """Refuse to boot if connectors are configured but the token-vault
    encryption key is empty. Detection is by presence of OAuth client IDs —
    see Q2 in the S1 design doc. Dev environments without any connector
    creds still boot fine."""
    connector_enabled = bool(s.GOOGLE_CLIENT_ID) or bool(s.SLACK_CLIENT_ID)
    if connector_enabled and not s.ENCRYPTION_KEY:
        which = []
        if s.GOOGLE_CLIENT_ID:
            which.append("GOOGLE_CLIENT_ID")
        if s.SLACK_CLIENT_ID:
            which.append("SLACK_CLIENT_ID")
        raise RuntimeError(
            "Refusing to start: connector credentials are set ("
            + ", ".join(which)
            + ") but ENCRYPTION_KEY is empty. Set ENCRYPTION_KEY (Fernet key) "
            "to enable token-vault encryption, or unset the connector "
            "credentials to disable the connectors entirely."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail loud if connectors are configured but token-vault isn't.
    _validate_connector_secrets(settings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_app_startup_validation.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run all unit tests to confirm no regression**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -q`
Expected: all pass.

- [ ] **Step 6: Manual sanity check — the running app still loads**

Run: `cd backend && .venv/bin/python -c "from app.main import app; print(len(app.routes))"`
Expected: prints the route count (was 64; still 64).

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/unit/test_app_startup_validation.py
git commit -m "feat(S1): fail-loud startup if connectors enabled without ENCRYPTION_KEY"
```

---

## Task 7: `EmailIndexRepository.upsert_many` — chunked commits

**Files:**
- Modify: `backend/app/infrastructure/db/repositories/email_index_repo.py`
- Modify (extend, don't create): `backend/tests/integration/test_repositories.py` (or new file if you prefer; this plan extends the existing one)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_repositories.py`:

```python


async def test_email_index_upsert_many_persists_in_chunks(db, make_proposal_db):
    """upsert_many must commit per chunk so a later failure does not lose
    rows that were already added."""
    from datetime import datetime, timezone
    from app.infrastructure.db.models.base import _uuid_default
    from app.infrastructure.db.models.email_index import EmailIndex
    from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository

    agency, _client, _proposal = await make_proposal_db()
    repo = EmailIndexRepository(db)

    now = datetime.now(timezone.utc)
    rows = [
        EmailIndex(
            id=_uuid_default(),
            agency_id=str(agency.id),
            gmail_message_id=f"msg-{i}",
            gmail_thread_id=f"thr-{i}",
            client_domain="example.com",
            client_name="Example",
            message_type="general",
            sentiment="neutral",
            priority="medium",
            summary=f"summary {i}",
            entities={},
            from_address="x@example.com",
            to_addresses=["us@nuprop.dev"],
            subject=f"hello {i}",
            date=now,
            has_attachments=False,
            synced_at=now,
        )
        for i in range(7)
    ]
    written = await repo.upsert_many(rows, chunk_size=3)
    assert written == 7
    # All visible after the call
    count = await repo.count_by_agency(agency.id)
    assert count == 7


async def test_email_index_upsert_many_empty_list_returns_zero(db):
    from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository
    repo = EmailIndexRepository(db)
    assert await repo.upsert_many([], chunk_size=50) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_repositories.py::test_email_index_upsert_many_persists_in_chunks tests/integration/test_repositories.py::test_email_index_upsert_many_empty_list_returns_zero -v`
Expected: FAIL with `AttributeError: 'EmailIndexRepository' object has no attribute 'upsert_many'`.

- [ ] **Step 3: Add the method to `EmailIndexRepository`**

Append to `backend/app/infrastructure/db/repositories/email_index_repo.py`, inside the `EmailIndexRepository` class (before the final blank line at EOF):

```python

    async def upsert_many(
        self, rows: list[EmailIndex], chunk_size: int = 50,
    ) -> int:
        """Persist a list of EmailIndex rows in chunks, committing each chunk.

        This bounds the rollback blast radius: a failure mid-way through one
        chunk loses at most `chunk_size` rows, while everything committed
        before is preserved. Caller is expected to have already filtered out
        duplicates (use `get_existing_message_ids` first).
        """
        if not rows:
            return 0
        written = 0
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            self.session.add_all(chunk)
            await self.session.commit()
            written += len(chunk)
        return written
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_repositories.py::test_email_index_upsert_many_persists_in_chunks tests/integration/test_repositories.py::test_email_index_upsert_many_empty_list_returns_zero -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/db/repositories/email_index_repo.py backend/tests/integration/test_repositories.py
git commit -m "feat(S1): EmailIndexRepository.upsert_many — chunked commits"
```

---

## Task 8: ConnectorViewModel — swap encryption to TokenVault + injectability + logger

**Files:**
- Modify: `backend/app/viewmodels/connector_viewmodel.py`

- [ ] **Step 1: Modify the file in three localized edits**

**Edit 1 (top imports + module logger):** Replace the existing import block at the top of `backend/app/viewmodels/connector_viewmodel.py` (lines 1-22) with:

```python
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConnectorAuthError, TokenVaultError
from app.infrastructure.db.models.base import _uuid_default
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository
from app.infrastructure.external.gcal_client import GCalClient
from app.infrastructure.external.gdrive_client import GDriveClient
from app.infrastructure.external.gmail_client import GmailClient
from app.infrastructure.external.slack_client import SlackClient
from app.infrastructure.security.token_vault import TokenVault
from app.services.ai.email_classifier import EmailClassifier
from app.viewmodels.shared.viewmodel import ViewModelBase

logger = logging.getLogger(__name__)

FREEMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com", "protonmail.com"}
```

**Edit 2 (constructor — accept injected vault and clients):** Replace the existing `__init__` (lines 26-32) with:

```python
    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        *,
        gmail_client: GmailClient | None = None,
        slack_client: SlackClient | None = None,
        token_vault: TokenVault | None = None,
    ):
        super().__init__(request, db)
        self._gmail = gmail_client or GmailClient()
        self._slack = slack_client or SlackClient()
        if token_vault is not None:
            self._vault = token_vault
        else:
            from app.core.deps import get_token_vault
            self._vault = get_token_vault()
        self._agency_repo: AgencyRepository | None = None
        self._client_repo: ClientRepository | None = None
        self._email_repo: EmailIndexRepository | None = None
```

**Edit 3 (replace `_encrypt`/`_decrypt`):** Replace the existing `_encrypt`/`_decrypt` methods (the section under `# ── Token encryption ─────────────────────────────────────`, lines 51-65) with:

```python
    # ── Token encryption ─────────────────────────────────────

    def _encrypt(self, text: str) -> str:
        """Encrypt via the injected TokenVault. Raises TokenVaultError if the
        vault is not configured; the route handler converts that to 5xx."""
        return self._vault.encrypt(text)

    def _decrypt(self, text: str) -> str:
        """Decrypt via the injected TokenVault. Raises TokenVaultError on
        InvalidToken (rotated key / corruption); caller maps that to
        ConnectorAuthError("needs_reauth")."""
        return self._vault.decrypt(text)
```

- [ ] **Step 2: Run the existing test suite to ensure no behavioral regression**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 244 + 16 = 260 passing (previous baseline + tests added in Tasks 1, 3, 4, 6, 7).

The vault swap is transparent: in tests `ENCRYPTION_KEY=""` so the vault raises if encrypt/decrypt is called — but the existing tests don't exercise the connector OAuth/sync paths, so they don't reach those calls. Verify this assumption holds.

- [ ] **Step 3: Commit**

```bash
git add backend/app/viewmodels/connector_viewmodel.py
git commit -m "refactor(S1): ConnectorViewModel uses TokenVault + accepts injected clients"
```

---

## Task 9: ConnectorViewModel — OAuth state on auth-url + handle_callback (Gmail)

**Files:**
- Modify: `backend/app/viewmodels/connector_viewmodel.py`

- [ ] **Step 1: Replace `get_auth_url` + `handle_callback`**

In `backend/app/viewmodels/connector_viewmodel.py`, find the section under `# ── OAuth flow ───────────────────────────────────────────` (currently lines 67-99). Replace both `get_auth_url` and `handle_callback`:

```python
    # ── OAuth flow ───────────────────────────────────────────

    async def get_auth_url(self, agency_id: UUID) -> str:
        from app.core.config import get_settings
        from app.infrastructure.security.oauth_state import issue_state

        if not self._gmail.is_configured:
            self.error = "Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
            self.status_code = 400
            return ""
        state = issue_state(
            agency_id=agency_id,
            provider="gmail",
            secret=get_settings().JWT_SECRET_KEY,
        )
        return self._gmail.get_auth_url(state)

    async def handle_callback(self, agency_id_from_state: UUID, code: str) -> dict:
        """Caller (route handler) must have already verified the OAuth state
        token and resolved the agency_id from its payload — do NOT trust the
        URL/session for agency_id during the callback."""
        try:
            tokens = await self._gmail.exchange_code(code)
        except Exception as exc:
            logger.exception(
                "gmail.exchange_code failed",
                extra={"event": "connector.gmail.exchange_failed"},
            )
            self.error = "Google rejected the authorization code"
            self.status_code = 400
            return {}

        access_token = tokens.get("access_token") or ""
        refresh_token = tokens.get("refresh_token") or ""
        if not access_token or not refresh_token:
            logger.warning(
                "gmail.exchange_code returned without refresh_token",
                extra={"event": "connector.gmail.missing_refresh_token"},
            )
            self.error = (
                "Google did not return a refresh token. "
                "Revoke the existing app authorization in your Google account and try again."
            )
            self.status_code = 400
            return {}

        try:
            email = await self._gmail.get_user_email(access_token)
        except Exception as exc:
            logger.exception(
                "gmail.get_user_email failed",
                extra={"event": "connector.gmail.profile_failed"},
            )
            self.error = "Failed to read Google profile"
            self.status_code = 502
            return {}

        agency = await self.agency_repo.get_by_id(agency_id_from_state)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
            return {}

        try:
            encrypted_refresh = self._encrypt(refresh_token)
        except TokenVaultError:
            self.error = "Server encryption key is not configured; cannot store credentials"
            self.status_code = 500
            return {}

        settings = dict(agency.settings or {})
        settings["gmail"] = {
            "connected": True,
            "email": email,
            "refresh_token": encrypted_refresh,
            "last_sync": None,
            "email_count": 0,
        }
        await self.agency_repo.update(agency_id_from_state, settings=settings)

        return {"connected": True, "email": email, "last_sync": None, "email_count": 0}
```

- [ ] **Step 2: Run existing connector-adjacent tests** to confirm no regression on what's tested

Run: `cd backend && .venv/bin/python -m pytest tests/integration -q`
Expected: existing integration tests still pass (no test currently exercises `get_auth_url`/`handle_callback`, so this is a sanity run).

- [ ] **Step 3: Commit**

```bash
git add backend/app/viewmodels/connector_viewmodel.py
git commit -m "feat(S1): Gmail OAuth — issue signed state, verify in callback, validate response"
```

---

## Task 10: ConnectorViewModel — OAuth state for Slack + same hardening

**Files:**
- Modify: `backend/app/viewmodels/connector_viewmodel.py`

- [ ] **Step 1: Replace `get_slack_auth_url` + `handle_slack_callback`**

In `backend/app/viewmodels/connector_viewmodel.py`, find the section starting `# ── Slack ────────────────────────────────────────────────` and replace `get_slack_auth_url` and `handle_slack_callback`:

```python
    # ── Slack ────────────────────────────────────────────────

    async def get_slack_auth_url(self, agency_id: UUID) -> str:
        from app.core.config import get_settings
        from app.infrastructure.security.oauth_state import issue_state

        if not self._slack.is_configured:
            self.error = "Slack OAuth not configured"
            self.status_code = 400
            return ""
        state = issue_state(
            agency_id=agency_id,
            provider="slack",
            secret=get_settings().JWT_SECRET_KEY,
        )
        return self._slack.get_auth_url(state)

    async def handle_slack_callback(self, agency_id_from_state: UUID, code: str) -> dict:
        """Caller (route handler) must have already verified the OAuth state
        token and resolved the agency_id from its payload."""
        try:
            data = await self._slack.exchange_code(code)
        except Exception:
            logger.exception(
                "slack.exchange_code failed",
                extra={"event": "connector.slack.exchange_failed"},
            )
            return {}

        access_token = data.get("access_token", "")
        team = data.get("team", {})
        workspace_name = team.get("name", "")
        if not access_token:
            logger.warning(
                "slack.exchange_code returned without access_token",
                extra={"event": "connector.slack.missing_access_token"},
            )
            return {}

        agency = await self.agency_repo.get_by_id(agency_id_from_state)
        if not agency:
            return {}

        try:
            encrypted_access = self._encrypt(access_token)
        except TokenVaultError:
            logger.exception(
                "token vault not configured during Slack callback",
                extra={"event": "connector.slack.vault_not_configured"},
            )
            return {}

        settings = dict(agency.settings or {})
        settings["slack"] = {
            "connected": True,
            "workspace": workspace_name,
            "access_token": encrypted_access,
            "last_sync": None,
        }
        await self.agency_repo.update(agency_id_from_state, settings=settings)

        return {"connected": True, "workspace": workspace_name}
```

Note: this method also replaces the `slack = SlackClient()` inline instantiation that was at the top of the original `handle_slack_callback`; we now use `self._slack` (injected in `__init__`).

Also find `get_slack_status` (currently around line 396) and replace the inline `slack = SlackClient()` with `self._slack`:

```python
    async def get_slack_status(self, agency_id: UUID) -> dict:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return {"connected": False}
        slack_settings = (agency.settings or {}).get("slack", {})
        return {
            "connected": slack_settings.get("connected", False),
            "configured": self._slack.is_configured,
            "workspace": slack_settings.get("workspace"),
            "last_sync": slack_settings.get("last_sync"),
        }
```

- [ ] **Step 2: Run the suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: still green (no test for Slack OAuth flow exists yet).

- [ ] **Step 3: Commit**

```bash
git add backend/app/viewmodels/connector_viewmodel.py
git commit -m "feat(S1): Slack OAuth — issue signed state, verify in callback, validate response"
```

---

## Task 11: ConnectorViewModel — narrow excepts in disconnect / sync paths + logger

**Files:**
- Modify: `backend/app/viewmodels/connector_viewmodel.py`

- [ ] **Step 1: Replace the `disconnect` method**

Find the existing `disconnect` method (currently `try: ... except Exception: pass` for `revoke_token`). Replace it:

```python
    async def disconnect(self, agency_id: UUID) -> None:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return

        gmail = (agency.settings or {}).get("gmail", {})
        if gmail.get("refresh_token"):
            try:
                token = self._decrypt(gmail["refresh_token"])
                await self._gmail.revoke_token(token)
            except TokenVaultError:
                logger.warning(
                    "skipping Gmail token revoke — stored token could not be decrypted",
                    extra={"event": "connector.gmail.disconnect_decrypt_failed"},
                )
            except Exception:
                logger.exception(
                    "Gmail token revoke failed; clearing local credentials anyway",
                    extra={"event": "connector.gmail.revoke_failed"},
                )

        settings = dict(agency.settings or {})
        settings.pop("gmail", None)
        await self.agency_repo.update(agency_id, settings=settings)
        await self.email_repo.delete_by_agency(agency_id)
```

- [ ] **Step 2: Replace the per-domain sync loop's `except`** inside `sync_emails`

Find the existing `for domain, client_name in domain_map.items():` block, and locate the `except Exception: continue` at the bottom of that loop. Replace the entire `try/except` body (NOT the rewrite for per-domain commit — that's Task 12) with this narrower except:

The current block ends:

```python
            except Exception:
                continue  # Don't let one domain failure stop the whole sync
```

Replace with:

```python
            except ConnectorAuthError:
                # Token was bad — propagate up so the caller surfaces "reconnect required"
                raise
            except Exception:
                logger.exception(
                    "Gmail sync failed for one domain; skipping and continuing",
                    extra={"event": "connector.gmail.domain_sync_failed", "domain": domain},
                )
                continue
```

- [ ] **Step 3: Replace the `except Exception: continue` in `sync_drive` and `sync_calendar` and `sync_slack` the same way**

In `sync_drive` (currently `except Exception: continue` around line 306-307):

```python
            except Exception:
                logger.exception(
                    "Drive sync failed for one client; skipping",
                    extra={"event": "connector.drive.client_sync_failed", "client_id": str(client.id)},
                )
                continue
```

In `sync_calendar` (line ~358-359):

```python
            except Exception:
                logger.exception(
                    "Calendar sync failed for one client; skipping",
                    extra={"event": "connector.calendar.client_sync_failed", "client_id": str(client.id)},
                )
                continue
```

In `sync_slack` (line ~470-471):

```python
            except Exception:
                logger.exception(
                    "Slack sync failed for one client; skipping",
                    extra={"event": "connector.slack.client_sync_failed", "client_id": str(client.id)},
                )
                continue
```

- [ ] **Step 4: Also narrow the `try/except` in `sync_emails`'s `last_sync` ISO parse**

Find:

```python
        if gmail.get("last_sync"):
            try:
                since = datetime.fromisoformat(str(gmail["last_sync"]))
            except Exception:
                pass
```

Replace with:

```python
        if gmail.get("last_sync"):
            try:
                since = datetime.fromisoformat(str(gmail["last_sync"]))
            except ValueError:
                logger.warning(
                    "last_sync ISO parse failed; running full sync",
                    extra={
                        "event": "connector.gmail.bad_last_sync_iso",
                        "value": str(gmail["last_sync"]),
                    },
                )
```

- [ ] **Step 5: Run the suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: still green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/viewmodels/connector_viewmodel.py
git commit -m "refactor(S1): narrow excepts in connector sync paths, add structured logging"
```

---

## Task 12: ConnectorViewModel — `sync_emails` rewrite for per-domain commit + watermark

**Files:**
- Modify: `backend/app/viewmodels/connector_viewmodel.py`
- Create: `backend/tests/integration/test_email_sync_resumption.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_email_sync_resumption.py`:

```python
"""S1 resumption test: when sync_emails persists per domain and writes a
per-domain watermark, a mid-sync failure preserves the domains processed
before the failure and the next run picks up only the remaining ones."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.viewmodels.connector_viewmodel import ConnectorViewModel
from cryptography.fernet import Fernet


class _FakeGmail:
    """In-process stand-in for GmailClient."""

    def __init__(self, *, by_domain: dict[str, list[dict]], fail_domains: set[str] | None = None):
        self.is_configured = True
        self._by_domain = by_domain
        self._fail = fail_domains or set()
        self.refresh_calls = 0

    async def refresh_access_token(self, refresh_token: str) -> str:
        self.refresh_calls += 1
        return "fresh-access-token"

    async def fetch_messages_for_domain(self, access_token, domain, since, limit):
        if domain in self._fail:
            raise RuntimeError(f"simulated upstream failure for {domain}")
        return self._by_domain.get(domain, [])


def _msg(i: int, domain: str) -> dict:
    return {
        "id": f"msg-{domain}-{i}",
        "thread_id": f"thr-{domain}-{i}",
        "from": f"contact-{i}@{domain}",
        "to": "us@nuprop.dev",
        "subject": f"hi {i}",
        "snippet": "snippet",
        "date": datetime(2026, 5, 16, 10, 0, 0, tzinfo=timezone.utc),
        "has_attachments": False,
    }


@pytest.fixture
def _vault_key():
    return Fernet.generate_key().decode()


async def _setup_agency_with_two_clients(db, make_proposal_db):
    agency, _, _ = await make_proposal_db()
    from app.infrastructure.db.repositories.agency_repo import AgencyRepository
    from app.infrastructure.db.repositories.client_repo import ClientRepository

    client_repo = ClientRepository(db)
    await client_repo.update(
        (await client_repo.search(agency.id, limit=10))[0].id,
        contacts=[{"email": "alice@example-a.com"}, {"email": "bob@example-a.com"}],
    )
    other = await client_repo.create(
        agency_id=agency.id, name="ClientB", slug="client-b",
    )
    await client_repo.update(other.id, contacts=[{"email": "ann@example-b.com"}])

    await AgencyRepository(db).update(
        agency.id,
        settings={
            "gmail": {
                "connected": True,
                "email": "owner@nuprop.dev",
                "refresh_token": Fernet(Fernet.generate_key()).encrypt(b"placeholder").decode(),
                "last_sync": None,
                "email_count": 0,
            }
        },
    )
    await db.commit()
    return agency


async def test_partial_failure_preserves_prior_domain_progress(
    db, make_proposal_db, monkeypatch, _vault_key,
):
    """Domain A succeeds, Domain B raises. Domain A's emails must be
    persisted and Domain A's watermark must be set; the next run must skip A
    (already watermarked) and successfully process B."""
    from app.infrastructure.security.token_vault import TokenVault
    from app.services.ai import email_classifier as ec_mod

    # The VM uses the injected vault, so we don't touch the global settings.
    agency = await _setup_agency_with_two_clients(db, make_proposal_db)
    real_vault = TokenVault(key=_vault_key)
    settings = dict(agency.settings)
    settings["gmail"]["refresh_token"] = real_vault.encrypt("dummy-refresh-token")
    from app.infrastructure.db.repositories.agency_repo import AgencyRepository
    await AgencyRepository(db).update(agency.id, settings=settings)
    await db.commit()

    # Patch the email classifier to return deterministic results without LLM
    async def _fake_classify_batch(self, msgs, concurrency=5):  # noqa: ANN001
        return [
            {
                "message_type": "general",
                "sentiment": "neutral",
                "priority": "medium",
                "summary": "stub",
                "entities": {},
            }
            for _ in msgs
        ]
    monkeypatch.setattr(ec_mod.EmailClassifier, "classify_batch", _fake_classify_batch)

    fake_gmail = _FakeGmail(
        by_domain={
            "example-a.com": [_msg(1, "example-a.com"), _msg(2, "example-a.com")],
            "example-b.com": [_msg(1, "example-b.com")],
        },
        fail_domains={"example-b.com"},
    )

    request = AsyncMock()
    vm = ConnectorViewModel(
        request, db, gmail_client=fake_gmail, token_vault=real_vault,
    )
    result = await vm.sync_emails(agency.id)

    # Domain A persisted, B errored but did not lose A
    from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository
    repo = EmailIndexRepository(db)
    assert await repo.count_by_agency(agency.id) == 2
    assert "example-a.com" in result["domains_synced"]
    assert "example-b.com" not in result["domains_synced"]

    # Watermark recorded for A
    refreshed = await AgencyRepository(db).get_by_id(agency.id)
    per_domain = (
        (refreshed.settings or {}).get("gmail", {}).get("last_sync_per_domain") or {}
    )
    assert "example-a.com" in per_domain

    # Second run: B now succeeds, A is skipped (watermark says it's done)
    fake_gmail._fail.clear()  # noqa: SLF001 — test-only
    result2 = await vm.sync_emails(agency.id)
    assert "example-b.com" in result2["domains_synced"]
    assert await repo.count_by_agency(agency.id) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_email_sync_resumption.py -v`
Expected: FAIL — either the rewrite isn't in place yet, or the test fails on the watermark assertion because the current code stores only a coarse `last_sync`.

- [ ] **Step 3: Rewrite `sync_emails`**

In `backend/app/viewmodels/connector_viewmodel.py`, replace the entire `sync_emails` method (currently around lines 137-238) with:

```python
    async def sync_emails(self, agency_id: UUID) -> dict:
        start = time.time()

        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
            return {}

        gmail = (agency.settings or {}).get("gmail", {})
        if not gmail.get("connected") or not gmail.get("refresh_token"):
            self.error = "Gmail not connected"
            self.status_code = 400
            return {}

        try:
            refresh_token = self._decrypt(gmail["refresh_token"])
        except TokenVaultError:
            self.error = "Stored Gmail credentials could not be decrypted; please reconnect"
            self.status_code = 401
            return {}

        try:
            access_token = await self._gmail.refresh_access_token(refresh_token)
        except Exception:
            logger.exception(
                "gmail.refresh_access_token failed",
                extra={"event": "connector.gmail.refresh_failed"},
            )
            self.error = "Failed to refresh Google access token; please reconnect"
            self.status_code = 401
            return {}

        clients = await self.client_repo.search(agency_id, limit=500)
        domain_map = self._extract_domains(clients)
        if not domain_map:
            return {"new_emails": 0, "total_emails": 0, "domains_synced": [], "duration_seconds": 0}

        per_domain_watermark: dict[str, str] = dict(
            gmail.get("last_sync_per_domain") or {}
        )
        classifier = EmailClassifier()
        total_new = 0
        synced_domains: list[str] = []

        for domain, client_name in domain_map.items():
            # Per-domain `since` from the watermark (falls back to None)
            since: datetime | None = None
            iso = per_domain_watermark.get(domain)
            if iso:
                try:
                    since = datetime.fromisoformat(iso)
                except ValueError:
                    logger.warning(
                        "per-domain last_sync ISO parse failed; running full sync for domain",
                        extra={
                            "event": "connector.gmail.bad_per_domain_iso",
                            "domain": domain,
                            "value": iso,
                        },
                    )

            try:
                messages = await self._gmail.fetch_messages_for_domain(
                    access_token, domain, since, limit=100,
                )
                if not messages:
                    continue

                msg_ids = [m["id"] for m in messages]
                existing = await self.email_repo.get_existing_message_ids(agency_id, msg_ids)
                new_messages = [m for m in messages if m["id"] not in existing]

                if not new_messages:
                    synced_domains.append(domain)
                    # Even with no new messages, advance the per-domain watermark
                    per_domain_watermark[domain] = datetime.now(timezone.utc).isoformat()
                    await self._persist_gmail_watermark(agency_id, per_domain_watermark)
                    continue

                classifications = await classifier.classify_batch(new_messages, concurrency=5)

                now = datetime.now(timezone.utc)
                rows = []
                from app.infrastructure.db.models.email_index import EmailIndex
                for msg, cls in zip(new_messages, classifications):
                    rows.append(EmailIndex(
                        id=_uuid_default(),
                        agency_id=str(agency_id),
                        gmail_message_id=msg["id"],
                        gmail_thread_id=msg.get("thread_id", ""),
                        client_domain=domain,
                        client_name=client_name,
                        message_type=cls["message_type"],
                        sentiment=cls["sentiment"],
                        priority=cls["priority"],
                        summary=cls["summary"],
                        entities=cls["entities"],
                        from_address=msg.get("from", ""),
                        to_addresses=msg.get("to", "").split(",") if msg.get("to") else [],
                        subject=msg.get("subject", ""),
                        date=msg["date"] if isinstance(msg["date"], datetime) else now,
                        has_attachments=msg.get("has_attachments", False),
                        synced_at=now,
                    ))

                # Persist this domain's emails in chunks, committing as we go
                await self.email_repo.upsert_many(rows, chunk_size=50)

                # Advance per-domain watermark to the newest persisted email's date
                newest_iso = max(
                    (m["date"] for m in new_messages if isinstance(m.get("date"), datetime)),
                    default=now,
                ).isoformat()
                per_domain_watermark[domain] = newest_iso
                await self._persist_gmail_watermark(agency_id, per_domain_watermark)

                total_new += len(new_messages)
                synced_domains.append(domain)

            except ConnectorAuthError:
                raise
            except Exception:
                logger.exception(
                    "Gmail sync failed for one domain; skipping and continuing",
                    extra={"event": "connector.gmail.domain_sync_failed", "domain": domain},
                )
                continue

        # Final refresh of the coarse last_sync + email_count for the UI
        await self._persist_gmail_watermark(agency_id, per_domain_watermark)
        email_count = await self.email_repo.count_by_agency(agency_id)
        agency = await self.agency_repo.get_by_id(agency_id)
        settings = dict(agency.settings or {})
        gmail_settings = dict(settings.get("gmail", {}))
        gmail_settings["email_count"] = email_count
        settings["gmail"] = gmail_settings
        await self.agency_repo.update(agency_id, settings=settings)

        duration = round(time.time() - start, 1)
        return {
            "new_emails": total_new,
            "total_emails": email_count,
            "domains_synced": synced_domains,
            "duration_seconds": duration,
        }

    async def _persist_gmail_watermark(
        self, agency_id: UUID, per_domain: dict[str, str],
    ) -> None:
        """Write the per-domain watermark map AND the coarse last_sync to the
        agency's settings JSON, committing immediately so a later domain
        failure cannot revert it."""
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return
        settings = dict(agency.settings or {})
        gmail = dict(settings.get("gmail", {}))
        gmail["last_sync_per_domain"] = per_domain
        if per_domain:
            gmail["last_sync"] = min(per_domain.values())
        else:
            gmail["last_sync"] = datetime.now(timezone.utc).isoformat()
        settings["gmail"] = gmail
        await self.agency_repo.update(agency_id, settings=settings)
        await self._db.commit()
```

- [ ] **Step 4: Run the resumption test**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_email_sync_resumption.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 244 + (Tasks 1, 3, 4, 6, 7) + 1 = 261+ passing. No regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/viewmodels/connector_viewmodel.py backend/tests/integration/test_email_sync_resumption.py
git commit -m "feat(S1): per-domain commits and watermarks in Gmail sync"
```

---

## Task 13: Route handlers — verify OAuth state in `connectors.py`

**Files:**
- Modify: `backend/app/views/v1/connectors.py`
- Create: `backend/tests/integration/test_gmail_oauth_csrf.py`
- Create: `backend/tests/integration/test_slack_oauth_csrf.py`

- [ ] **Step 1: Write the failing tests for Gmail CSRF**

Create `backend/tests/integration/test_gmail_oauth_csrf.py`:

```python
"""S1: Gmail OAuth callback must reject forged, expired, and replayed `state`.

None of these tests reach the encryption step — they all fail before
ConnectorViewModel.handle_callback runs (state validation 400) OR the
handle_callback is stubbed via monkeypatch (replay test). So no ENCRYPTION_KEY
is needed."""

from __future__ import annotations

from app.core.config import get_settings
from app.infrastructure.security.oauth_state import issue_state
from tests.conftest import API


async def test_callback_rejects_missing_state(client, registered):
    resp = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": ""},
    )
    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


async def test_callback_rejects_forged_state(client, registered):
    resp = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": "deadbeef.cafebabe"},
    )
    assert resp.status_code == 400


async def test_callback_rejects_state_for_wrong_provider(client, registered):
    from uuid import UUID
    secret = get_settings().JWT_SECRET_KEY
    # State issued for slack but submitted to gmail
    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="slack",
        secret=secret,
    )
    resp = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert resp.status_code == 400


async def test_callback_rejects_expired_state(client, registered):
    from uuid import UUID
    secret = get_settings().JWT_SECRET_KEY
    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="gmail",
        secret=secret,
        ttl_seconds=-1,  # already expired
    )
    resp = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert resp.status_code == 400


async def test_callback_rejects_replayed_state(client, registered, monkeypatch):
    """First use returns 400 because we have no real OAuth code; second use
    must also fail, but with 'replayed' as the reason — proving the nonce
    store recorded the first use."""
    from uuid import UUID

    # We don't want the test to hit Google with the bogus code. Patch
    # ConnectorViewModel.handle_callback to short-circuit AFTER state has been
    # verified, so the nonce is still marked.
    from app.viewmodels import connector_viewmodel
    async def _ok(self, agency_id_from_state, code):
        return {"connected": True, "email": "x@x.test", "last_sync": None, "email_count": 0}
    monkeypatch.setattr(connector_viewmodel.ConnectorViewModel, "handle_callback", _ok)

    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="gmail",
        secret=get_settings().JWT_SECRET_KEY,
    )
    r1 = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert r1.status_code == 200, r1.text
    r2 = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert r2.status_code == 400
    assert "replay" in r2.json()["detail"].lower() or "state" in r2.json()["detail"].lower()


async def test_auth_url_includes_signed_state(client, registered, monkeypatch):
    """The auth-url response must contain a `state` parameter that verify_state can decode."""
    # gmail.is_configured must return True for the route to issue a URL
    from app.infrastructure.external.gmail_client import GmailClient
    monkeypatch.setattr(GmailClient, "is_configured", property(lambda self: True))
    # Also stub the actual auth URL builder so we get a deterministic URL
    monkeypatch.setattr(GmailClient, "get_auth_url", lambda self, state: f"https://accounts.google.com/o/oauth2/v2/auth?state={state}")

    resp = await client.get(f"{API}/connectors/gmail/auth-url", headers=registered.headers)
    assert resp.status_code == 200
    url = resp.json()["auth_url"]
    assert "state=" in url
    state = url.split("state=")[-1]
    assert "." in state  # body.signature shape
```

- [ ] **Step 2: Write the failing tests for Slack CSRF**

Create `backend/tests/integration/test_slack_oauth_csrf.py`:

```python
"""S1: Slack OAuth callback must reject forged, expired, replayed `state`."""

from __future__ import annotations

from app.core.config import get_settings
from app.infrastructure.security.oauth_state import issue_state
from tests.conftest import API


async def test_slack_callback_rejects_forged_state(client, registered):
    resp = await client.post(
        f"{API}/connectors/slack/callback",
        headers=registered.headers,
        json={"code": "x", "state": "garbage.bytes"},
    )
    assert resp.status_code == 400


async def test_slack_callback_rejects_state_for_wrong_provider(client, registered):
    from uuid import UUID
    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="gmail",
        secret=get_settings().JWT_SECRET_KEY,
    )
    resp = await client.post(
        f"{API}/connectors/slack/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert resp.status_code == 400


async def test_slack_callback_rejects_replayed_state(client, registered, monkeypatch):
    from uuid import UUID
    from app.viewmodels import connector_viewmodel
    async def _ok(self, agency_id_from_state, code):
        return {"connected": True, "workspace": "Test"}
    monkeypatch.setattr(connector_viewmodel.ConnectorViewModel, "handle_slack_callback", _ok)

    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="slack",
        secret=get_settings().JWT_SECRET_KEY,
    )
    r1 = await client.post(
        f"{API}/connectors/slack/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert r1.status_code == 200, r1.text
    r2 = await client.post(
        f"{API}/connectors/slack/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert r2.status_code == 400
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_gmail_oauth_csrf.py tests/integration/test_slack_oauth_csrf.py -v`
Expected: most fail — the routes still trust the URL-supplied agency_id and don't verify state.

- [ ] **Step 4: Modify `backend/app/views/v1/connectors.py`**

Replace the file with the following. This (a) uses signed state instead of `agency_id` from the auth header for the callback identity, (b) wires `nonce_store` via DI, (c) maps `OAuthStateError` to `HTTPException(400)`:

```python
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_agency_id, get_nonce_store
from app.core.errors import OAuthStateError
from app.domain.schemas.connector_schemas import (
    GmailAuthUrlResponse,
    GmailCallbackRequest,
    GmailStatusResponse,
    GmailSyncResponse,
)
from app.infrastructure.db.database import get_db
from app.infrastructure.security.oauth_state import NonceStore, verify_state
from app.viewmodels.connector_viewmodel import ConnectorViewModel

router = APIRouter(prefix="/connectors", tags=["connectors"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> ConnectorViewModel:
    return ConnectorViewModel(request, db)


async def _verified_agency_from_state(
    state: str, provider: str, nonce_store: NonceStore,
) -> UUID:
    if not state:
        raise HTTPException(status_code=400, detail="missing oauth state")
    try:
        return await verify_state(
            token=state,
            expected_provider=provider,
            secret=get_settings().JWT_SECRET_KEY,
            nonce_store=nonce_store,
        )
    except OAuthStateError as exc:
        raise HTTPException(status_code=400, detail=f"invalid oauth state ({exc.code})")


@router.get("/gmail/auth-url", response_model=GmailAuthUrlResponse)
async def gmail_auth_url(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    url = await vm.get_auth_url(agency_id)
    if not url:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return GmailAuthUrlResponse(auth_url=url)


@router.post("/gmail/callback", response_model=GmailStatusResponse)
async def gmail_callback(
    body: GmailCallbackRequest,
    vm: ConnectorViewModel = Depends(get_vm),
    nonce_store: NonceStore = Depends(get_nonce_store),
):
    agency_id = await _verified_agency_from_state(body.state, "gmail", nonce_store)
    result = await vm.handle_callback(agency_id, body.code)
    if not result:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return GmailStatusResponse(**result)


@router.get("/gmail/status", response_model=GmailStatusResponse)
async def gmail_status(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    return GmailStatusResponse(**(await vm.get_status(agency_id)))


@router.post("/gmail/sync", response_model=GmailSyncResponse)
async def gmail_sync(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.sync_emails(agency_id)
    if not result and vm.error:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return GmailSyncResponse(**result)


@router.delete("/gmail", status_code=status.HTTP_204_NO_CONTENT)
async def gmail_disconnect(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    await vm.disconnect(agency_id)


# ── Google Drive ─────────────────────────────────────────

@router.post("/drive/sync")
async def drive_sync(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.sync_drive(agency_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Google Calendar ──────────────────────────────────────

@router.post("/calendar/sync")
async def calendar_sync(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.sync_calendar(agency_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Slack ────────────────────────────────────────────────

@router.get("/slack/auth-url")
async def slack_auth_url(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    url = await vm.get_slack_auth_url(agency_id)
    if not url:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return {"auth_url": url}


@router.post("/slack/callback")
async def slack_callback(
    body: GmailCallbackRequest,
    vm: ConnectorViewModel = Depends(get_vm),
    nonce_store: NonceStore = Depends(get_nonce_store),
):
    agency_id = await _verified_agency_from_state(body.state, "slack", nonce_store)
    result = await vm.handle_slack_callback(agency_id, body.code)
    if not result:
        raise HTTPException(status_code=400, detail="Slack connection failed")
    return result


@router.get("/slack/status")
async def slack_status(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    return await vm.get_slack_status(agency_id)


@router.post("/slack/sync")
async def slack_sync(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.sync_slack(agency_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/slack", status_code=status.HTTP_204_NO_CONTENT)
async def slack_disconnect(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    await vm.disconnect_slack(agency_id)
```

- [ ] **Step 5: Run the CSRF tests**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_gmail_oauth_csrf.py tests/integration/test_slack_oauth_csrf.py -v`
Expected: 9 passed (6 Gmail + 3 Slack).

- [ ] **Step 6: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/app/views/v1/connectors.py \
        backend/tests/integration/test_gmail_oauth_csrf.py \
        backend/tests/integration/test_slack_oauth_csrf.py
git commit -m "feat(S1): connector route handlers verify OAuth state (Gmail + Slack)"
```

---

## Task 14: `clients.py` — `ContextService` via `Depends()` instead of inline

**Files:**
- Modify: `backend/app/views/v1/clients.py`
- Create: `backend/tests/integration/test_clients_context_di.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_clients_context_di.py`:

```python
"""S1: `POST /clients/{id}/context` must use the injected ContextService so
tests can override it without monkeypatching."""

from __future__ import annotations

from app.core.deps import get_context_service
from app.main import app
from tests.conftest import API


class _FakeContextService:
    def __init__(self):
        self.calls = []

    async def extract_context(self, raw_text: str) -> dict:
        self.calls.append(("extract", raw_text))
        return {"relationship": {"status": "warm_intro"}}

    async def merge_context(self, existing: dict, new_extraction: dict) -> dict:
        self.calls.append(("merge", existing, new_extraction))
        return {**existing, **new_extraction}

    async def generate_context_brief(self, client_name: str, profile: dict) -> str:
        return f"brief for {client_name}"

    async def enrich_context_with_emails(self, profile, emails):
        return profile


async def test_add_context_uses_injected_service(client, registered):
    fake = _FakeContextService()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        c = await client.post(
            f"{API}/clients", headers=registered.headers,
            json={"name": "Acme Co"},
        )
        client_id = c.json()["id"]
        resp = await client.post(
            f"{API}/clients/{client_id}/context",
            headers=registered.headers,
            json={"raw_text": "some pasted email text"},
        )
        assert resp.status_code == 200
        assert fake.calls[0][0] == "extract"
        assert fake.calls[0][1] == "some pasted email text"
        assert fake.calls[1][0] == "merge"
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_context_brief_uses_injected_service(client, registered):
    fake = _FakeContextService()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        c = await client.post(
            f"{API}/clients", headers=registered.headers, json={"name": "Acme Co"},
        )
        client_id = c.json()["id"]
        # Seed context via the same injected fake
        await client.post(
            f"{API}/clients/{client_id}/context",
            headers=registered.headers,
            json={"raw_text": "seed"},
        )
        resp = await client.get(
            f"{API}/clients/{client_id}/context-brief",
            headers=registered.headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_context"] is True
        assert body["brief"] == "brief for Acme Co"
    finally:
        app.dependency_overrides.pop(get_context_service, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_clients_context_di.py -v`
Expected: FAIL — the routes currently `from app.services.context_service import ContextService; svc = ContextService()` inline, ignoring the override.

- [ ] **Step 3: Modify `backend/app/views/v1/clients.py`**

In `backend/app/views/v1/clients.py`, replace the two route handlers `add_context` and `get_context_brief` (currently lines 82-155) with versions that take `ctx: ContextService = Depends(get_context_service)`:

```python
@router.post("/{client_id}/context", response_model=ClientResponse)
async def add_context(
    client_id: UUID,
    body: ContextInput,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ClientViewModel = Depends(get_vm),
    ctx: ContextService = Depends(get_context_service),
):
    """Parse pasted text into structured context and merge into client profile."""
    client = await vm.get_client(client_id, agency_id)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)

    # Extract structured context from pasted text
    extraction = await ctx.extract_context(body.raw_text)

    # Merge with existing context profile
    existing = client.context_profile or {}
    merged = await ctx.merge_context(existing, extraction)

    # Save to client
    updated = await vm.update_client(client_id, agency_id, ClientUpdate(context_profile=merged))  # type: ignore
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update context")
    return updated


@router.get("/{client_id}/context-brief")
async def get_context_brief(
    client_id: UUID,
    include_emails: bool = False,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ClientViewModel = Depends(get_vm),
    ctx: ContextService = Depends(get_context_service),
    db: AsyncSession = Depends(get_db),
):
    """Generate a natural-language Context Brief. Optionally enriches with email data."""
    client = await vm.get_client(client_id, agency_id)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)

    context_profile = client.context_profile or {}

    email_count = 0
    if include_emails and client.contacts:
        try:
            from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository
            email_repo = EmailIndexRepository(db)
            domains = [
                c["email"].split("@")[-1].lower()
                for c in (client.contacts if isinstance(client.contacts, list) else [])
                if isinstance(c, dict) and c.get("email") and "@" in c["email"]
            ]
            if domains:
                emails = await email_repo.get_recent_for_domains(client.agency_id, domains, limit=20)
                email_count = len(emails)
                if emails:
                    email_dicts = [
                        {"summary": e.summary, "message_type": e.message_type, "sentiment": e.sentiment, "subject": e.subject, "date": str(e.date)}
                        for e in emails
                    ]
                    context_profile = await ctx.enrich_context_with_emails(context_profile, email_dicts)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "email enrichment for context brief failed; continuing without emails",
                extra={"event": "context.brief.email_enrichment_failed"},
            )

    if not context_profile:
        return {"brief": "", "has_context": False, "email_count": email_count}

    brief = await ctx.generate_context_brief(client.name, context_profile)
    return {"brief": brief, "has_context": True, "email_count": email_count}
```

And update the top-of-file imports — add `from app.core.deps import get_context_service` and `from app.services.context_service import ContextService`:

Find the existing import block at the top of `backend/app/views/v1/clients.py`:

```python
from app.core.deps import get_current_agency_id
from app.domain.schemas.client_schemas import ClientCreate, ClientResponse, ClientUpdate
from app.infrastructure.db.database import get_db
from app.viewmodels.client_viewmodel import ClientViewModel
```

Replace with:

```python
from app.core.deps import get_context_service, get_current_agency_id
from app.domain.schemas.client_schemas import ClientCreate, ClientResponse, ClientUpdate
from app.infrastructure.db.database import get_db
from app.services.context_service import ContextService
from app.viewmodels.client_viewmodel import ClientViewModel
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_clients_context_di.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/views/v1/clients.py backend/tests/integration/test_clients_context_di.py
git commit -m "feat(S1): inject ContextService via Depends() in clients routes"
```

---

## Task 15: Module loggers + narrow excepts — `gmail_client.py`

**Files:**
- Modify: `backend/app/infrastructure/external/gmail_client.py`

- [ ] **Step 1: Add the module logger and narrow the four excepts**

Edit `backend/app/infrastructure/external/gmail_client.py`:

**Edit A — add logger after the imports.** Find:

```python
from app.core.config import get_settings


class GmailClient:
```

Replace with:

```python
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GmailClient:
```

**Edit B — narrow `revoke_token`.** Find:

```python
    async def revoke_token(self, token: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.OAUTH_REVOKE_URL, params={"token": token})
        except Exception:
            pass  # Best effort
```

Replace with:

```python
    async def revoke_token(self, token: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.OAUTH_REVOKE_URL, params={"token": token})
        except httpx.HTTPError as exc:
            logger.warning(
                "gmail token revoke failed (best-effort)",
                extra={"event": "connector.gmail.revoke_http_error", "error": str(exc)},
            )
```

**Edit C — narrow `get_message` date parse.** Find:

```python
        date_str = headers.get("date", "")
        try:
            date = parsedate_to_datetime(date_str)
        except Exception:
            date = datetime.now()
```

Replace with:

```python
        date_str = headers.get("date", "")
        try:
            date = parsedate_to_datetime(date_str)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "gmail message date parse failed; defaulting to now()",
                extra={
                    "event": "connector.gmail.bad_date",
                    "raw": date_str[:40],
                    "error": str(exc),
                },
            )
            date = datetime.now()
```

**Edit D — narrow `fetch_messages_for_domain` per-message except.** Find:

```python
            for ref in msg_refs:
                try:
                    msg = await self.get_message(access_token, ref["id"])
                    all_messages.append(msg)
                except Exception:
                    continue
```

Replace with:

```python
            for ref in msg_refs:
                try:
                    msg = await self.get_message(access_token, ref["id"])
                    all_messages.append(msg)
                except (httpx.HTTPError, KeyError) as exc:
                    logger.warning(
                        "gmail get_message failed for one ref; skipping",
                        extra={
                            "event": "connector.gmail.message_fetch_failed",
                            "ref_id": ref.get("id"),
                            "error": str(exc),
                        },
                    )
                    continue
```

- [ ] **Step 2: Run the full suite to confirm no regression**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add backend/app/infrastructure/external/gmail_client.py
git commit -m "refactor(S1): gmail_client — module logger + narrowed excepts"
```

---

## Task 16: Module loggers — `slack_client.py`, `gdrive_client.py`, `gcal_client.py`

**Files:**
- Modify: `backend/app/infrastructure/external/slack_client.py`
- Modify: `backend/app/infrastructure/external/gdrive_client.py`
- Modify: `backend/app/infrastructure/external/gcal_client.py`

- [ ] **Step 1: Add module logger to `slack_client.py`** — `SlackClient` is already clean (raises `ValueError` on `not ok`), so the logger is the only required change.

Find the top of `backend/app/infrastructure/external/slack_client.py`:

```python
from app.core.config import get_settings


class SlackClient:
```

Replace with:

```python
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SlackClient:
```

- [ ] **Step 2: Add module logger to `gdrive_client.py` and narrow the export-failure except**

Open `backend/app/infrastructure/external/gdrive_client.py`. Add `import logging` to the top imports and `logger = logging.getLogger(__name__)` after the existing imports (mirror the pattern from Task 15 / Step 1).

Then find the existing `try/except` around the export call. Replace any `except Exception: return ""` block with:

```python
        except httpx.HTTPError as exc:
            logger.warning(
                "Drive document export failed; returning empty content",
                extra={
                    "event": "connector.drive.export_failed",
                    "file_id": file_id,
                    "error": str(exc),
                },
            )
            return ""
```

(Read the file first to confirm the exact `try/except` shape — the export call is the one preceded by a `try:` and followed by `return r.text[:5000]`.)

- [ ] **Step 3: Add module logger to `gcal_client.py`**

Mirror Step 1 — add `import logging` and `logger = logging.getLogger(__name__)`. No except changes required.

- [ ] **Step 4: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/external/slack_client.py \
        backend/app/infrastructure/external/gdrive_client.py \
        backend/app/infrastructure/external/gcal_client.py
git commit -m "refactor(S1): module loggers on slack/drive/calendar clients; narrow drive export except"
```

---

## Task 17: Module loggers + narrow excepts — `services/context_service.py`, `services/context_intelligence.py`

**Files:**
- Modify: `backend/app/services/context_service.py`
- Modify: `backend/app/services/context_intelligence.py`

- [ ] **Step 1: `context_service.py` — add logger and narrow line 227**

Open `backend/app/services/context_service.py`. Add `import logging` at the top of imports and `logger = logging.getLogger(__name__)` after them.

Find the `enrich_context_with_emails` method. At the end it has:

```python
        try:
            result = await self._llm.complete_json(
                ...
            )
            if isinstance(result, dict):
                return await self.merge_context(context_profile, result)
        except Exception:
            pass

        return context_profile
```

Replace the `except` clause with:

```python
        except Exception:
            logger.exception(
                "email enrichment via LLM failed; returning original profile",
                extra={"event": "context_service.email_enrichment_failed"},
            )

        return context_profile
```

- [ ] **Step 2: `context_intelligence.py` — add logger and narrow date-parse excepts**

Open `backend/app/services/context_intelligence.py`. Add `import logging` at the top and `logger = logging.getLogger(__name__)` after the dataclass/import block.

Find the two `try/except Exception: pass` blocks around `datetime.fromisoformat(...)`. Replace each `except` clause with:

For the first one (around line 88-89, on `_sources` parsing):

```python
                except (ValueError, TypeError) as exc:
                    logger.debug(
                        "context_intelligence: bad sync_dt in _sources, skipping recency contribution",
                        extra={
                            "event": "context_intelligence.bad_sync_dt",
                            "value": str(last_sync)[:40],
                            "error": str(exc),
                        },
                    )
```

For the second one (around line 103-104, on past_work date parsing):

```python
                except (ValueError, TypeError) as exc:
                    logger.debug(
                        "context_intelligence: bad past_work date, skipping",
                        extra={
                            "event": "context_intelligence.bad_past_work_date",
                            "value": str(date_str)[:40],
                            "error": str(exc),
                        },
                    )
```

- [ ] **Step 3: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/context_service.py backend/app/services/context_intelligence.py
git commit -m "refactor(S1): module loggers on context_service + context_intelligence"
```

---

## Task 18: Module logger — `email_index_repo.py`

**Files:**
- Modify: `backend/app/infrastructure/db/repositories/email_index_repo.py`

- [ ] **Step 1: Add the logger**

Open `backend/app/infrastructure/db/repositories/email_index_repo.py`. Add `import logging` at the top of imports and `logger = logging.getLogger(__name__)` after them. No except changes needed — the repo is clean.

- [ ] **Step 2: Run the suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add backend/app/infrastructure/db/repositories/email_index_repo.py
git commit -m "refactor(S1): add module logger to email_index_repo"
```

---

## Task 19: Acceptance checklist — verify shipped state

**Files:** none modified (verification only).

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 244 baseline + ≥18 new tests, all passing, none skipped.

- [ ] **Step 2: Run the frontend test suite (zero regression)**

Run: `cd frontend && pnpm test --run`
Expected: 131 passing across 24 files. No new failures.

- [ ] **Step 3: Grep — confirm no bare `except Exception` survives in M16-M20 files**

Run:

```bash
grep -rn "except Exception" \
  backend/app/services/context_service.py \
  backend/app/services/context_intelligence.py \
  backend/app/viewmodels/connector_viewmodel.py \
  backend/app/infrastructure/external/gmail_client.py \
  backend/app/infrastructure/external/gdrive_client.py \
  backend/app/infrastructure/external/gcal_client.py \
  backend/app/infrastructure/external/slack_client.py
```

Expected: any remaining `except Exception` lines must be followed by `logger.exception(...)` or `logger.warning(...)`. NO bare `except Exception: pass` or `except Exception: continue`.

- [ ] **Step 4: Grep — confirm `import logging` is present in every M16-M20 file**

Run:

```bash
grep -L "^import logging\|^from logging" \
  backend/app/services/context_service.py \
  backend/app/services/context_intelligence.py \
  backend/app/viewmodels/connector_viewmodel.py \
  backend/app/infrastructure/external/gmail_client.py \
  backend/app/infrastructure/external/gdrive_client.py \
  backend/app/infrastructure/external/gcal_client.py \
  backend/app/infrastructure/external/slack_client.py \
  backend/app/infrastructure/db/repositories/email_index_repo.py
```

Expected: no output — every file is matched, meaning every file imports logging.

- [ ] **Step 5: Manual startup check — connectors enabled, no `ENCRYPTION_KEY` → app refuses to start**

Run:

```bash
cd backend && GOOGLE_CLIENT_ID="test-id" ENCRYPTION_KEY="" .venv/bin/python -c "
import asyncio
from app.main import app, lifespan
async def main():
    async with lifespan(app):
        pass
asyncio.run(main())
"
```

Expected: `RuntimeError: Refusing to start: connector credentials are set (GOOGLE_CLIENT_ID) but ENCRYPTION_KEY is empty. ...`

- [ ] **Step 6: Manual startup check — connectors enabled, `ENCRYPTION_KEY` set → app boots fine**

Run:

```bash
cd backend && GOOGLE_CLIENT_ID="test-id" \
    ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
    .venv/bin/python -c "
import asyncio
from app.main import app, lifespan
async def main():
    async with lifespan(app):
        print('lifespan started ok')
asyncio.run(main())
"
```

Expected: prints `lifespan started ok` (and possibly some seed-template log lines).

- [ ] **Step 7: Update the project memory + handoff**

Append a one-line update to `docs/superpowers/HANDOFF.md` (under the S0-S6 table) marking S1 as DONE.

Update `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/project_build_progress.md` and `session_handoff_2026_05_16.md` to flip the S1 row to DONE and set "Active slice" to S2.

- [ ] **Step 8: Merge worktree → main**

When the user approves at the checkpoint:

```bash
# From the worktree:
git log --oneline origin/main..HEAD   # confirm the S1 commits
# Then from the main checkout:
cd /Users/karthikramesh/Developer/nuprop
git fetch origin
git merge --ff-only worktree-m16-m20-s1-backend-hardening
git push origin main
```

(The auto-deploy from Option A will pick this up. Doc + logging-only changes are safe to ship to prod immediately; the OAuth/state changes are inert in prod until S4 sets the connector secrets.)

---

## What lands next

After S1 merges and the user approves at the S1 checkpoint:

- Open worktree `m16-m20-s2-context-ui`.
- Write spec `docs/superpowers/specs/2026-05-DD-s2-context-ui-design.md`.
- Implement the Manual Context UI on the Client Detail page so M16 is shippable end-to-end. Aims to be 1 day.

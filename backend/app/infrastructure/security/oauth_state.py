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
    is embedded and checked automatically by `verify_state`."""
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

    # Expiry (C1: validate exp is numeric before use)
    try:
        exp = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "oauth_state.verify rejected payload with invalid exp field",
            extra={"event": "security.oauth_state.malformed"},
        )
        raise OAuthStateError(
            code="malformed",
            message="state payload has invalid exp field",
            cause=exc,
        ) from exc
    if exp < int(time.time()):
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

    # Parse agency_id BEFORE consuming the nonce — failure must not burn the slot (C2).
    try:
        agency_id = UUID(payload["agency_id"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "oauth_state.verify rejected payload with invalid agency_id",
            extra={"event": "security.oauth_state.malformed"},
        )
        raise OAuthStateError(
            code="malformed",
            message="state payload has invalid agency_id",
            cause=exc,
        ) from exc

    # Replay (this consumes the nonce — only do it after all parse failures) (I1)
    nonce = payload.get("nonce")
    if not nonce:
        logger.warning(
            "oauth_state.verify rejected payload missing nonce",
            extra={"event": "security.oauth_state.malformed"},
        )
        raise OAuthStateError(code="malformed", message="state payload missing nonce field")

    ttl_remaining = max(60, exp - int(time.time()))
    if not await nonce_store.mark_seen(nonce, ttl_seconds=ttl_remaining):
        logger.warning(
            "oauth_state.verify rejected replayed nonce",
            extra={"event": "security.oauth_state.replayed"},
        )
        raise OAuthStateError(code="replayed", message="state token nonce has already been used")

    return agency_id

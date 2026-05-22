"""Shared HTTP retry/backoff for the connector clients.

All four connector clients (Gmail, Drive, Calendar, Slack) route their
requests through ``request_with_retry`` so the retry policy lives in one
place. Retries 429/5xx and transport errors; never retries other 4xx —
a 401 ``invalid_grant`` must surface to the caller unchanged.
"""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_ATTEMPTS = 4
_BACKOFF_BASE = 0.5
_BACKOFF_JITTER = 0.5
_MAX_RETRY_AFTER = 60.0  # never sleep longer than this from a Retry-After header

# Indirection so tests can stub out the actual waiting without touching the
# global asyncio.sleep.
_sleep = asyncio.sleep


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter. ``attempt`` is 1-based."""
    return _BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, _BACKOFF_JITTER)


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Honor a numeric ``Retry-After`` header (capped); otherwise exponential backoff."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(int(retry_after)), _MAX_RETRY_AFTER)
        except ValueError:
            pass
    return _backoff(attempt)


async def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    transport: httpx.AsyncBaseTransport | None = None,
    **kwargs,
) -> httpx.Response:
    """Issue an HTTP request, retrying transient failures.

    Retries on 429/5xx and ``httpx.TransportError`` with exponential backoff
    (honoring ``Retry-After``). Raises ``httpx.HTTPStatusError`` on a
    non-retryable status, or on a 5xx that survives every attempt; raises the
    last ``httpx.TransportError`` if transport errors exhaust the attempts.

    ``transport`` is a test seam — production callers leave it ``None``.
    """
    last_transport_exc: httpx.TransportError | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                response = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            last_transport_exc = exc
            if attempt >= max_attempts:
                break
            delay = _backoff(attempt)
            logger.warning(
                "connector http transport error; retrying",
                extra={
                    "event": "connector.retry",
                    "url": url,
                    "attempt": attempt,
                    "delay": round(delay, 2),
                    "error": str(exc),
                },
            )
            await _sleep(delay)
            continue

        if response.status_code in RETRYABLE_STATUS and attempt < max_attempts:
            delay = _retry_delay(response, attempt)
            logger.warning(
                "connector http retryable status; retrying",
                extra={
                    "event": "connector.retry",
                    "url": url,
                    "status": response.status_code,
                    "attempt": attempt,
                    "delay": round(delay, 2),
                },
            )
            await _sleep(delay)
            continue

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "connector http request failed",
                extra={
                    "event": "connector.retry.exhausted",
                    "url": url,
                    "status": response.status_code,
                    "attempts": attempt,
                },
            )
            raise
        return response

    logger.error(
        "connector http request exhausted retries",
        extra={"event": "connector.retry.exhausted", "url": url, "attempts": max_attempts},
    )
    if last_transport_exc is None:
        raise RuntimeError("retry loop exhausted with no transport exception")
    raise last_transport_exc

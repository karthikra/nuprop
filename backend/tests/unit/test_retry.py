from __future__ import annotations

import httpx
import pytest

from app.infrastructure.external import _retry
from app.infrastructure.external._retry import request_with_retry


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make backoff instant so retry tests don't actually wait."""

    async def _instant(_seconds):
        return None

    monkeypatch.setattr(_retry, "_sleep", _instant)


def _counting_handler(script):
    """httpx.MockTransport handler yielding `script` entries in order.
    Each entry is an int status, a (status, headers) tuple, or an Exception
    to raise. The last entry repeats once the script is exhausted."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        item = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            status, headers = item
            return httpx.Response(status, headers=headers)
        return httpx.Response(item)

    return handler, calls


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    handler, calls = _counting_handler([429, 200])
    resp = await request_with_retry(
        "GET", "https://x.test/y", transport=httpx.MockTransport(handler)
    )
    assert resp.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_does_not_retry_on_401():
    handler, calls = _counting_handler([401, 200])
    with pytest.raises(httpx.HTTPStatusError):
        await request_with_retry(
            "GET", "https://x.test/y", transport=httpx.MockTransport(handler)
        )
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_raises_after_exhausting_attempts_on_503():
    handler, calls = _counting_handler([503])
    with pytest.raises(httpx.HTTPStatusError):
        await request_with_retry(
            "GET", "https://x.test/y",
            transport=httpx.MockTransport(handler), max_attempts=3,
        )
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retries_on_transport_error():
    handler, calls = _counting_handler([httpx.ConnectError("boom"), 200])
    resp = await request_with_retry(
        "GET", "https://x.test/y", transport=httpx.MockTransport(handler)
    )
    assert resp.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_honors_retry_after_header(monkeypatch):
    seen: list[float] = []

    async def _record(seconds):
        seen.append(seconds)

    monkeypatch.setattr(_retry, "_sleep", _record)
    handler, _ = _counting_handler([(429, {"Retry-After": "7"}), 200])
    resp = await request_with_retry(
        "GET", "https://x.test/y", transport=httpx.MockTransport(handler)
    )
    assert resp.status_code == 200
    assert seen == [7.0]

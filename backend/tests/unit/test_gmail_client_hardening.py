from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.infrastructure.external.gmail_client import GmailClient


# Safety bound: if the iteration cap is missing the loop is infinite, so the
# fake raises after 200 calls — the test then FAILS cleanly instead of hanging.
_SAFETY_BOUND = 200


@pytest.mark.asyncio
async def test_fetch_messages_for_domain_bounded_when_pagetoken_never_ends():
    """Google returning 0 results with a perpetually non-null pageToken must
    not loop forever — the iteration cap stops it."""
    client = GmailClient()
    calls = {"n": 0}

    async def fake_search(_self, _access_token, _q, _max_results, _page_token):
        calls["n"] += 1
        if calls["n"] > _SAFETY_BOUND:
            raise AssertionError("pagination did not terminate — no iteration cap")
        return [], "endless-token"

    with patch.object(GmailClient, "search_messages", new=fake_search):
        out = await client.fetch_messages_for_domain("tok", "acme.com", limit=200)

    assert out == []
    assert calls["n"] == 50  # MAX_PAGE_ITERATIONS — bounded, not infinite


@pytest.mark.asyncio
async def test_fetch_recent_messages_bounded_when_pagetoken_never_ends():
    client = GmailClient()
    calls = {"n": 0}

    async def fake_search(_self, _access_token, _q, _max_results, _page_token):
        calls["n"] += 1
        if calls["n"] > _SAFETY_BOUND:
            raise AssertionError("pagination did not terminate — no iteration cap")
        return [], "endless-token"

    with patch.object(GmailClient, "search_messages", new=fake_search):
        out = await client.fetch_recent_messages("tok", lookback_days=30, limit=200)

    assert out == []
    assert calls["n"] == 50


@pytest.mark.asyncio
async def test_get_message_returns_none_date_on_unparseable_header():
    """An unparseable Date header must not be disguised as a real
    timestamp — get_message returns date=None and lets the persistence
    layer apply its timezone-aware fallback."""
    client = GmailClient()
    payload = {
        "id": "m1",
        "threadId": "t1",
        "snippet": "",
        "payload": {
            "headers": [
                {"name": "From", "value": "a@acme.com"},
                {"name": "Date", "value": "not-a-real-date"},
            ]
        },
    }

    async def fake_retry(_method, _url, **_kwargs):
        return SimpleNamespace(json=lambda: payload)

    with patch(
        "app.infrastructure.external.gmail_client.request_with_retry", new=fake_retry
    ):
        msg = await client.get_message("tok", "m1")

    assert msg["date"] is None

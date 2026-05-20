from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.infrastructure.external.gmail_client import GmailClient


@pytest.mark.asyncio
async def test_fetch_recent_messages_builds_after_query_and_paginates() -> None:
    client = GmailClient()
    pages = [
        ([{"id": "a"}, {"id": "b"}], "tok1"),
        ([{"id": "c"}], None),
    ]
    captured_queries: list[str] = []

    async def fake_search(_self, _access_token, q, max_results, page_token):
        captured_queries.append(q)
        return pages.pop(0)

    async def fake_get(_self, _access_token, msg_id):
        return {
            "id": msg_id,
            "thread_id": f"t-{msg_id}",
            "from": "x@example.com",
            "to": "",
            "subject": "hi",
            "snippet": "",
            "date": datetime(2026, 5, 1, tzinfo=timezone.utc),
            "has_attachments": False,
        }

    with (
        patch.object(GmailClient, "search_messages", new=fake_search),
        patch.object(GmailClient, "get_message", new=fake_get),
    ):
        out = await client.fetch_recent_messages("token", lookback_days=30, limit=500)

    assert {m["id"] for m in out} == {"a", "b", "c"}
    assert all(q.startswith("after:") for q in captured_queries)


@pytest.mark.asyncio
async def test_fetch_recent_messages_respects_limit() -> None:
    client = GmailClient()
    call_count = {"n": 0}

    async def fake_search(_self, _access_token, q, max_results, page_token):
        call_count["n"] += 1
        return ([{"id": f"id-{i}-{call_count['n']}"} for i in range(max_results)], "tok")

    async def fake_get(_self, _access_token, msg_id):
        return {"id": msg_id, "thread_id": "", "from": "", "to": "",
                "subject": "", "snippet": "", "date": datetime.now(timezone.utc),
                "has_attachments": False}

    with (
        patch.object(GmailClient, "search_messages", new=fake_search),
        patch.object(GmailClient, "get_message", new=fake_get),
    ):
        out = await client.fetch_recent_messages("token", lookback_days=30, limit=150)

    assert len(out) == 150


@pytest.mark.asyncio
async def test_fetch_recent_messages_skips_bad_get_calls() -> None:
    client = GmailClient()

    async def fake_search(_self, _access_token, q, max_results, page_token):
        return ([{"id": "good"}, {"id": "bad"}, {"id": "good2"}], None)

    async def fake_get(_self, _access_token, msg_id):
        if msg_id == "bad":
            raise ValueError("boom")
        return {"id": msg_id, "thread_id": "", "from": "", "to": "",
                "subject": "", "snippet": "", "date": datetime.now(timezone.utc),
                "has_attachments": False}

    with (
        patch.object(GmailClient, "search_messages", new=fake_search),
        patch.object(GmailClient, "get_message", new=fake_get),
    ):
        out = await client.fetch_recent_messages("token", lookback_days=30, limit=10)

    assert {m["id"] for m in out} == {"good", "good2"}

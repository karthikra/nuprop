from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.infrastructure.external.gmail_client import GmailClient


@pytest.mark.asyncio
async def test_gmail_get_user_email_routes_through_retry_wrapper():
    client = GmailClient()
    captured: dict = {}

    async def fake_retry(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return SimpleNamespace(json=lambda: {"emailAddress": "me@acme.com"})

    with patch(
        "app.infrastructure.external.gmail_client.request_with_retry", new=fake_retry
    ):
        email = await client.get_user_email("tok")

    assert email == "me@acme.com"
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/users/me/profile")


from app.infrastructure.external.gcal_client import GCalClient
from app.infrastructure.external.gdrive_client import GDriveClient
from app.infrastructure.external.slack_client import SlackClient


@pytest.mark.asyncio
async def test_gdrive_search_files_routes_through_retry_wrapper():
    client = GDriveClient()
    captured: dict = {}

    async def fake_retry(method, url, **kwargs):
        captured["method"] = method
        return SimpleNamespace(json=lambda: {"files": [{"id": "f1"}]})

    with patch(
        "app.infrastructure.external.gdrive_client.request_with_retry", new=fake_retry
    ):
        files = await client.search_files("tok", "acme")

    assert files == [{"id": "f1"}]
    assert captured["method"] == "GET"


@pytest.mark.asyncio
async def test_gcal_search_events_routes_through_retry_wrapper():
    client = GCalClient()
    captured: dict = {}

    async def fake_retry(method, url, **kwargs):
        captured["method"] = method
        return SimpleNamespace(json=lambda: {"items": [{"id": "e1"}]})

    with patch(
        "app.infrastructure.external.gcal_client.request_with_retry", new=fake_retry
    ):
        events = await client.search_events("tok", "acme")

    assert events == [{"id": "e1"}]
    assert captured["method"] == "GET"


@pytest.mark.asyncio
async def test_slack_search_messages_routes_through_retry_wrapper():
    client = SlackClient()
    captured: dict = {}

    async def fake_retry(method, url, **kwargs):
        captured["method"] = method
        return SimpleNamespace(
            json=lambda: {"ok": True, "messages": {"matches": []}}
        )

    with patch(
        "app.infrastructure.external.slack_client.request_with_retry", new=fake_retry
    ):
        results = await client.search_messages("tok", "acme")

    assert results == []
    assert captured["method"] == "GET"

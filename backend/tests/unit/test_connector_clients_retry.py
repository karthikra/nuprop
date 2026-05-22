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

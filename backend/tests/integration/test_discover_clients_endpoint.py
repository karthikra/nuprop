"""Integration tests for POST /api/v1/connectors/gmail/discover-clients.

The tests use the standard `client` + `registered` fixtures from tests/conftest.py.
The `registered_agency_with_gmail` fixture builds on `registered` by:
  1. Updating the agency's settings with a connected Gmail entry whose
     refresh_token is Fernet-encrypted under a test key.
  2. Patching `app.core.deps.get_token_vault` so the VM (which calls it
     directly in __init__) uses the same test vault to decrypt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.security.token_vault import TokenVault
from tests.conftest import API


@pytest_asyncio.fixture
async def registered_agency_with_gmail(client, registered):
    """Registered agency with a connected Gmail entry (encrypted refresh token).

    Patches `app.core.deps.get_token_vault` so the ConnectorViewModel can
    decrypt the stored token without a real ENCRYPTION_KEY env var.
    """
    test_key = Fernet.generate_key().decode()
    vault = TokenVault(key=test_key)
    encrypted_token = vault.encrypt("dummy-refresh-token")

    # Write Gmail settings directly to the DB
    async with async_session_factory() as session:
        await AgencyRepository(session).update(
            UUID(registered.agency_id),
            settings={
                "gmail": {
                    "connected": True,
                    "refresh_token": encrypted_token,
                    "email": "owner@veeville.com",
                }
            },
        )
        await session.commit()

    # Patch get_token_vault at both call sites: deps module and the inline
    # import inside ConnectorViewModel.__init__ uses the same function object.
    with patch("app.core.deps.get_token_vault", return_value=vault):
        yield registered


@pytest.mark.asyncio
async def test_discover_endpoint_returns_candidates(
    client, registered_agency_with_gmail,
) -> None:
    fake_messages = [
        {
            "id": "1",
            "from": "Jane <jane@acme.com>",
            "to": "",
            "date": datetime(2026, 5, 1, tzinfo=timezone.utc),
        },
        {
            "id": "2",
            "from": "Bob <bob@acme.com>",
            "to": "",
            "date": datetime(2026, 5, 2, tzinfo=timezone.utc),
        },
    ]

    with (
        patch(
            "app.infrastructure.external.gmail_client.GmailClient.refresh_access_token",
            new=AsyncMock(return_value="access-tok"),
        ),
        patch(
            "app.infrastructure.external.gmail_client.GmailClient.fetch_recent_messages",
            new=AsyncMock(return_value=fake_messages),
        ),
    ):
        r = await client.post(
            f"{API}/connectors/gmail/discover-clients",
            headers=registered_agency_with_gmail.headers,
            json={"lookback_days": 90},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["domain"] == "acme.com"
    assert body["candidates"][0]["suggested_name"] == "Acme"
    assert body["scanned_messages"] == 2


@pytest.mark.asyncio
async def test_discover_endpoint_422_on_invalid_lookback(
    client, registered_agency_with_gmail,
) -> None:
    r = await client.post(
        f"{API}/connectors/gmail/discover-clients",
        headers=registered_agency_with_gmail.headers,
        json={"lookback_days": 7},  # not in {30, 90, 365}
    )
    assert r.status_code == 422  # pydantic Literal rejects it

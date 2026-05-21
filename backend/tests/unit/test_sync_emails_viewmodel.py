from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.errors import TokenVaultError
from app.viewmodels.connector_viewmodel import ConnectorViewModel


def _agency_with_gmail():
    return SimpleNamespace(
        id=uuid4(),
        settings={"gmail": {"connected": True, "refresh_token": "enc-token",
                            "email": "owner@veeville.com"}},
    )


@pytest.mark.asyncio
async def test_sync_emails_decrypt_failure_returns_400() -> None:
    """A stale stored Gmail credential is a 400, not a 401.

    401 would trip the frontend's global axios interceptor and log the user
    out; the session is fine — only the Gmail credential needs reconnecting.
    """
    agency = _agency_with_gmail()
    vm = ConnectorViewModel.__new__(ConnectorViewModel)
    vm.error = None
    vm.status_code = 200
    vm._agency_repo = MagicMock()
    vm._agency_repo.get_by_id = AsyncMock(return_value=agency)
    vm._decrypt = MagicMock(side_effect=TokenVaultError(code="decrypt_failed", message="x"))

    result = await vm.sync_emails(agency.id)

    assert result == {}
    assert vm.status_code == 400
    assert "decrypt" in vm.error.lower() or "reconnect" in vm.error.lower()


@pytest.mark.asyncio
async def test_sync_emails_refresh_failure_returns_400() -> None:
    """A rejected refresh token is also a 400 — same reasoning as decrypt."""
    agency = _agency_with_gmail()
    vm = ConnectorViewModel.__new__(ConnectorViewModel)
    vm.error = None
    vm.status_code = 200
    vm._agency_repo = MagicMock()
    vm._agency_repo.get_by_id = AsyncMock(return_value=agency)
    vm._decrypt = MagicMock(return_value="raw-token")
    vm._gmail = MagicMock()
    vm._gmail.refresh_access_token = AsyncMock(side_effect=RuntimeError("google rejected"))

    result = await vm.sync_emails(agency.id)

    assert result == {}
    assert vm.status_code == 400
    assert "reconnect" in vm.error.lower()

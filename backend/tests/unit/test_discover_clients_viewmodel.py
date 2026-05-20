from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.fixture
def agency_with_gmail():
    return SimpleNamespace(
        id=uuid4(),
        settings={"gmail": {"connected": True, "refresh_token": "enc-token",
                            "email": "owner@veeville.com"}},
    )


@pytest.mark.asyncio
async def test_discover_clients_returns_candidates_filtered_by_existing(
    agency_with_gmail,
) -> None:
    from app.viewmodels.connector_viewmodel import ConnectorViewModel

    vm = ConnectorViewModel.__new__(ConnectorViewModel)  # bypass __init__
    vm.error = None
    vm.status_code = 200

    mock_agency_repo = MagicMock()
    mock_agency_repo.get_by_id = AsyncMock(return_value=agency_with_gmail)
    vm._agency_repo = mock_agency_repo
    mock_client_repo = MagicMock()
    existing_client = SimpleNamespace(
        name="Tata", contacts=[{"name": "X", "email": "x@tatacomms.com"}],
    )
    mock_client_repo.search = AsyncMock(return_value=[existing_client])
    vm._client_repo = mock_client_repo

    vm._gmail = MagicMock()
    vm._gmail.refresh_access_token = AsyncMock(return_value="access")
    vm._gmail.fetch_recent_messages = AsyncMock(return_value=[
        {"id": "1", "from": "Jane <jane@acme.com>", "to": "",
         "date": datetime(2026, 5, 1, tzinfo=timezone.utc)},
        {"id": "2", "from": "Bob <bob@tatacomms.com>", "to": "",
         "date": datetime(2026, 5, 1, tzinfo=timezone.utc)},
    ])

    vm._decrypt = MagicMock(return_value="raw-token")

    resp = await vm.discover_clients(agency_with_gmail.id, lookback_days=90)

    domains = {c.domain for c in resp.candidates}
    assert domains == {"acme.com"}  # tatacomms.com filtered out as already-linked
    assert resp.excluded_existing == 1
    assert resp.scanned_messages == 2


@pytest.mark.asyncio
async def test_discover_clients_errors_when_gmail_not_connected() -> None:
    from app.viewmodels.connector_viewmodel import ConnectorViewModel

    vm = ConnectorViewModel.__new__(ConnectorViewModel)
    vm.error = None
    vm.status_code = 200

    agency = SimpleNamespace(id=uuid4(), settings={"gmail": {"connected": False}})
    mock_agency_repo = MagicMock()
    mock_agency_repo.get_by_id = AsyncMock(return_value=agency)
    vm._agency_repo = mock_agency_repo

    resp = await vm.discover_clients(agency.id, lookback_days=90)
    assert resp.candidates == []
    assert vm.error == "Gmail not connected"
    assert vm.status_code == 400


@pytest.mark.asyncio
async def test_discover_clients_handles_decrypt_failure() -> None:
    from app.core.errors import TokenVaultError
    from app.viewmodels.connector_viewmodel import ConnectorViewModel

    vm = ConnectorViewModel.__new__(ConnectorViewModel)
    vm.error = None
    vm.status_code = 200

    agency = SimpleNamespace(
        id=uuid4(),
        settings={"gmail": {"connected": True, "refresh_token": "bad", "email": "x@y.com"}},
    )
    mock_agency_repo = MagicMock()
    mock_agency_repo.get_by_id = AsyncMock(return_value=agency)
    vm._agency_repo = mock_agency_repo
    vm._decrypt = MagicMock(side_effect=TokenVaultError(code="decrypt_failed", message="x"))

    resp = await vm.discover_clients(agency.id, lookback_days=90)
    assert resp.candidates == []
    assert vm.status_code == 401
    assert "decrypt" in vm.error.lower() or "reconnect" in vm.error.lower()

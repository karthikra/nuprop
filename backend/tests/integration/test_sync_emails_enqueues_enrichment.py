"""S5 T9: sync_emails must enqueue enrich_context_from_emails after persisting
new email rows — one test per happy/sad path."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.viewmodels.connector_viewmodel import ConnectorViewModel
from cryptography.fernet import Fernet


# ── Shared helpers (mirror test_email_sync_resumption.py) ────────────────────

class _FakeGmail:
    """In-process stand-in for GmailClient."""

    def __init__(self, *, by_domain: dict[str, list[dict]]):
        self.is_configured = True
        self._by_domain = by_domain

    async def refresh_access_token(self, refresh_token: str) -> str:
        return "fresh-access-token"

    async def fetch_messages_for_domain(self, access_token, domain, since, limit):
        return self._by_domain.get(domain, [])


def _msg(i: int, domain: str) -> dict:
    return {
        "id": f"msg-{domain}-{i}",
        "thread_id": f"thr-{domain}-{i}",
        "from": f"contact-{i}@{domain}",
        "to": "us@nuprop.dev",
        "subject": f"hi {i}",
        "snippet": "snippet",
        "date": datetime(2026, 5, 16, 10, 0, 0, tzinfo=timezone.utc),
        "has_attachments": False,
    }


@pytest.fixture
def _vault_key():
    return Fernet.generate_key().decode()


async def _setup_agency_with_client(db, make_proposal_db, vault_key: str):
    """Create agency + one client whose contact domain is acme-corp.com."""
    agency, _, _ = await make_proposal_db()
    from app.infrastructure.db.repositories.agency_repo import AgencyRepository
    from app.infrastructure.db.repositories.client_repo import ClientRepository
    from app.infrastructure.security.token_vault import TokenVault

    real_vault = TokenVault(key=vault_key)
    client_repo = ClientRepository(db)

    # Update the auto-created client to have a contact email at acme-corp.com
    existing_clients = await client_repo.search(agency.id, limit=10)
    client = existing_clients[0]
    await client_repo.update(
        client.id,
        contacts=[{"email": "alice@acme-corp.com"}],
    )

    await AgencyRepository(db).update(
        agency.id,
        settings={
            "gmail": {
                "connected": True,
                "email": "owner@nuprop.dev",
                "refresh_token": real_vault.encrypt("dummy-refresh-token"),
                "last_sync": None,
                "email_count": 0,
            }
        },
    )
    await db.commit()
    return agency, client, real_vault


# ── Tests ────────────────────────────────────────────────────────────────────

async def test_sync_emails_enqueues_enrichment_for_clients_with_new_email(
    db, make_proposal_db, monkeypatch, _vault_key,
):
    """When sync_emails persists at least one new message for a client's domain,
    it must enqueue "enrich_context_from_emails" with the agency id and that
    client's id."""
    from app.services.ai import email_classifier as ec_mod

    agency, client, real_vault = await _setup_agency_with_client(
        db, make_proposal_db, _vault_key,
    )

    # Stub the classifier so it never hits the LLM
    async def _fake_classify_batch(self, msgs, concurrency=5):  # noqa: ANN001
        return [
            {
                "message_type": "general",
                "sentiment": "neutral",
                "priority": "medium",
                "summary": "stub",
                "entities": {},
            }
            for _ in msgs
        ]
    monkeypatch.setattr(ec_mod.EmailClassifier, "classify_batch", _fake_classify_batch)

    # One new message for acme-corp.com — same domain as the client's contact
    fake_gmail = _FakeGmail(
        by_domain={"acme-corp.com": [_msg(1, "acme-corp.com")]},
    )

    # Build the vm with a mock request; capture the ARQ pool mock
    request = AsyncMock()
    arq_pool_mock = AsyncMock()
    request.app.state.arq_pool = arq_pool_mock

    vm = ConnectorViewModel(
        request, db, gmail_client=fake_gmail, token_vault=real_vault,
    )
    result = await vm.sync_emails(agency.id)

    # The sync must have found the new email
    assert result["new_emails"] == 1

    # enqueue_job must have been called once with the right job name + args
    arq_pool_mock.enqueue_job.assert_called_once()
    call_args = arq_pool_mock.enqueue_job.call_args

    assert call_args.args[0] == "enrich_context_from_emails"
    assert call_args.args[1] == str(agency.id)
    assert str(client.id) in call_args.args[2]  # client_ids list


async def test_sync_emails_no_enqueue_when_no_new_email(
    db, make_proposal_db, monkeypatch, _vault_key,
):
    """When sync_emails fetches messages but they are all already persisted
    (empty new_messages), it must NOT enqueue enrich_context_from_emails."""
    from app.services.ai import email_classifier as ec_mod

    agency, client, real_vault = await _setup_agency_with_client(
        db, make_proposal_db, _vault_key,
    )

    async def _fake_classify_batch(self, msgs, concurrency=5):  # noqa: ANN001
        return [
            {
                "message_type": "general",
                "sentiment": "neutral",
                "priority": "medium",
                "summary": "stub",
                "entities": {},
            }
            for _ in msgs
        ]
    monkeypatch.setattr(ec_mod.EmailClassifier, "classify_batch", _fake_classify_batch)

    # Zero messages returned for the domain → no new_messages
    fake_gmail = _FakeGmail(
        by_domain={"acme-corp.com": []},
    )

    request = AsyncMock()
    arq_pool_mock = AsyncMock()
    request.app.state.arq_pool = arq_pool_mock

    vm = ConnectorViewModel(
        request, db, gmail_client=fake_gmail, token_vault=real_vault,
    )
    result = await vm.sync_emails(agency.id)

    assert result["new_emails"] == 0
    arq_pool_mock.enqueue_job.assert_not_called()

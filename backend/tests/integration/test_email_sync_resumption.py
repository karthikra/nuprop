"""S1 resumption test: when sync_emails persists per domain and writes a
per-domain watermark, a mid-sync failure preserves the domains processed
before the failure and the next run picks up only the remaining ones."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.viewmodels.connector_viewmodel import ConnectorViewModel
from cryptography.fernet import Fernet


class _FakeGmail:
    """In-process stand-in for GmailClient."""

    def __init__(self, *, by_domain: dict[str, list[dict]], fail_domains: set[str] | None = None):
        self.is_configured = True
        self._by_domain = by_domain
        self._fail = fail_domains or set()
        self.refresh_calls = 0

    async def refresh_access_token(self, refresh_token: str) -> str:
        self.refresh_calls += 1
        return "fresh-access-token"

    async def fetch_messages_for_domain(self, access_token, domain, since, limit):
        if domain in self._fail:
            raise RuntimeError(f"simulated upstream failure for {domain}")
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


async def _setup_agency_with_two_clients(db, make_proposal_db):
    agency, _, _ = await make_proposal_db()
    from app.infrastructure.db.repositories.agency_repo import AgencyRepository
    from app.infrastructure.db.repositories.client_repo import ClientRepository

    client_repo = ClientRepository(db)
    await client_repo.update(
        (await client_repo.search(agency.id, limit=10))[0].id,
        contacts=[{"email": "alice@example-a.com"}, {"email": "bob@example-a.com"}],
    )
    other = await client_repo.create(
        agency_id=agency.id, name="ClientB", slug="client-b",
    )
    await client_repo.update(other.id, contacts=[{"email": "ann@example-b.com"}])

    await AgencyRepository(db).update(
        agency.id,
        settings={
            "gmail": {
                "connected": True,
                "email": "owner@nuprop.dev",
                "refresh_token": Fernet(Fernet.generate_key()).encrypt(b"placeholder").decode(),
                "last_sync": None,
                "email_count": 0,
            }
        },
    )
    await db.commit()
    return agency


async def test_partial_failure_preserves_prior_domain_progress(
    db, make_proposal_db, monkeypatch, _vault_key,
):
    """Domain A succeeds, Domain B raises. Domain A's emails must be
    persisted and Domain A's watermark must be set; the next run must skip A
    (already watermarked) and successfully process B."""
    from app.infrastructure.security.token_vault import TokenVault
    from app.services.ai import email_classifier as ec_mod

    # The VM uses the injected vault, so we don't touch the global settings.
    agency = await _setup_agency_with_two_clients(db, make_proposal_db)
    real_vault = TokenVault(key=_vault_key)
    # Re-encrypt the stored placeholder under the real key
    from app.infrastructure.db.repositories.agency_repo import AgencyRepository
    settings = dict(agency.settings)
    settings["gmail"]["refresh_token"] = real_vault.encrypt("dummy-refresh-token")
    await AgencyRepository(db).update(agency.id, settings=settings)
    await db.commit()

    # Patch the email classifier to return deterministic results without LLM
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

    fake_gmail = _FakeGmail(
        by_domain={
            "example-a.com": [_msg(1, "example-a.com"), _msg(2, "example-a.com")],
            "example-b.com": [_msg(1, "example-b.com")],
        },
        fail_domains={"example-b.com"},
    )

    request = AsyncMock()
    vm = ConnectorViewModel(
        request, db, gmail_client=fake_gmail, token_vault=real_vault,
    )
    result = await vm.sync_emails(agency.id)

    # Domain A persisted, B errored but did not lose A
    from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository
    repo = EmailIndexRepository(db)
    assert await repo.count_by_agency(agency.id) == 2
    assert "example-a.com" in result["domains_synced"]
    assert "example-b.com" not in result["domains_synced"]

    # Watermark recorded for A
    refreshed = await AgencyRepository(db).get_by_id(agency.id)
    per_domain = (
        (refreshed.settings or {}).get("gmail", {}).get("last_sync_per_domain") or {}
    )
    assert "example-a.com" in per_domain

    # Second run: B now succeeds, A is skipped (watermark says it's done)
    fake_gmail._fail.clear()  # noqa: SLF001 — test-only
    result2 = await vm.sync_emails(agency.id)
    assert "example-b.com" in result2["domains_synced"]
    assert await repo.count_by_agency(agency.id) == 3

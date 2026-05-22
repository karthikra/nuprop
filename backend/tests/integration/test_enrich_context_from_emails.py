from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_enrich_processes_only_passed_clients(make_proposal_db, db, monkeypatch):
    """enrich_context_from_emails enriches only the given client_ids and updates context_profile."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})

    from app.infrastructure.db.models.email_index import EmailIndex
    row = EmailIndex(
        agency_id=str(agency.id),
        gmail_message_id=f"m-{uuid.uuid4()}",
        gmail_thread_id="t1",
        client_domain="acme.com",
        client_name=client.name,
        message_type="update",
        sentiment="positive",
        priority="medium",
        summary="Kickoff went well",
        entities={},
        from_address="jane@acme.com",
        to_addresses=[],
        subject="Kickoff",
        date=datetime(2026, 5, 1, tzinfo=timezone.utc),
        has_attachments=False,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    enrich_calls = {"summaries": []}

    async def fake_enrich(self, context_profile, email_summaries):
        enrich_calls["summaries"].append(email_summaries)
        return {**(context_profile or {}), "enriched": True}

    monkeypatch.setattr(
        "app.services.context_service.ContextService.enrich_context_with_emails", fake_enrich
    )

    from app.workers.enrichment import _enrich_clients
    await _enrich_clients(db, str(agency.id), [str(client.id)])

    from app.infrastructure.db.repositories.client_repo import ClientRepository
    refreshed = await ClientRepository(db).get_by_id(client.id)
    assert refreshed.context_profile.get("enriched") is True
    assert enrich_calls["summaries"][0][0]["subject"] == "Kickoff"
    assert enrich_calls["summaries"][0][0]["summary"] == "Kickoff went well"


@pytest.mark.asyncio
async def test_enrich_isolates_per_client_errors(make_proposal_db, db, monkeypatch):
    """One client raising does not abort the others / does not raise out."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})

    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz
    from app.infrastructure.db.models.email_index import EmailIndex
    db.add(EmailIndex(
        agency_id=str(agency.id), gmail_message_id=f"m-{_uuid.uuid4()}",
        gmail_thread_id="t1", client_domain="acme.com", client_name=client.name,
        message_type="update", sentiment="positive", priority="medium",
        summary="x", entities={}, from_address="a@acme.com", to_addresses=[],
        subject="s", date=_dt(2026, 5, 1, tzinfo=_tz.utc), has_attachments=False,
        synced_at=_dt.now(_tz.utc),
    ))
    await db.commit()

    async def boom(self, context_profile, email_summaries):
        raise RuntimeError("merge failed")

    monkeypatch.setattr(
        "app.services.context_service.ContextService.enrich_context_with_emails", boom
    )

    from app.workers.enrichment import _enrich_clients
    # Must NOT raise — per-client errors are caught.
    await _enrich_clients(db, str(agency.id), [str(client.id)])


@pytest.mark.asyncio
async def test_enrich_stamps_sources_email(make_proposal_db, db, monkeypatch):
    """_enrich_clients must stamp _sources['email'] on the context profile after enrichment.

    The stamp must mirror the shape Drive/Calendar/Slack use:
    {"email_count": <int>, "last_sync": <ISO timestamp str>}.
    fake_enrich returns a plain dict (no _sources); the stamp is applied by
    _enrich_clients itself, not by enrich_context_with_emails.
    """
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})

    from app.infrastructure.db.models.email_index import EmailIndex
    row = EmailIndex(
        agency_id=str(agency.id),
        gmail_message_id=f"m-{uuid.uuid4()}",
        gmail_thread_id="t-sources",
        client_domain="acme.com",
        client_name=client.name,
        message_type="update",
        sentiment="neutral",
        priority="low",
        summary="Sources stamp test",
        entities={},
        from_address="ops@acme.com",
        to_addresses=[],
        subject="Weekly update",
        date=datetime(2026, 5, 10, tzinfo=timezone.utc),
        has_attachments=False,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    async def fake_enrich(self, context_profile, email_summaries):
        # Return merged profile WITHOUT _sources — stamp must be added by _enrich_clients
        return {**(context_profile or {}), "enriched": True}

    monkeypatch.setattr(
        "app.services.context_service.ContextService.enrich_context_with_emails", fake_enrich
    )

    from app.workers.enrichment import _enrich_clients
    await _enrich_clients(db, str(agency.id), [str(client.id)])

    from app.infrastructure.db.repositories.client_repo import ClientRepository
    refreshed = await ClientRepository(db).get_by_id(client.id)
    profile = refreshed.context_profile

    # _sources["email"] must exist
    assert "_sources" in profile, "context_profile must have _sources key"
    assert "email" in profile["_sources"], "_sources must have 'email' key"

    email_source = profile["_sources"]["email"]
    # Must carry email_count (matching Drive's document_count / Slack's mention_count pattern)
    assert "email_count" in email_source, "_sources['email'] must carry 'email_count'"
    assert email_source["email_count"] == 1, "email_count should equal number of EmailIndex rows"
    # Must carry last_sync ISO timestamp (all other sources carry this)
    assert "last_sync" in email_source, "_sources['email'] must carry 'last_sync'"
    assert isinstance(email_source["last_sync"], str), "last_sync must be an ISO string"

"""Integration tests for the proposals API — CRUD, ownership, preferences."""

from __future__ import annotations

import uuid

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from tests.conftest import API


async def _create_client(http, headers, name="Proposal Client"):
    resp = await http.post(f"{API}/clients", headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_proposal(http, headers, client_id, name="Q3 Rebrand"):
    return await http.post(
        f"{API}/proposals",
        headers=headers,
        json={"client_id": client_id, "project_name": name},
    )


async def test_create_proposal(client, registered):
    c = await _create_client(client, registered.headers)
    resp = await _create_proposal(client, registered.headers, c["id"])
    assert resp.status_code == 201
    data = resp.json()
    assert data["project_name"] == "Q3 Rebrand"
    assert data["status"] == "draft"
    assert data["pipeline_state"]["current_phase"] == "brief"


async def test_create_proposal_with_missing_client_404(client, registered):
    resp = await _create_proposal(client, registered.headers, str(uuid.uuid4()))
    assert resp.status_code == 404


async def test_create_proposal_with_foreign_client_404(client, registered, second_agency):
    c = await _create_client(client, registered.headers)
    resp = await _create_proposal(client, second_agency.headers, c["id"])
    assert resp.status_code == 404


async def test_list_proposals_includes_client_name(client, registered):
    c = await _create_client(client, registered.headers)
    await _create_proposal(client, registered.headers, c["id"], "P1")
    await _create_proposal(client, registered.headers, c["id"], "P2")
    resp = await client.get(f"{API}/proposals", headers=registered.headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(p["client_name"] == "Proposal Client" for p in body)


async def test_get_proposal(client, registered):
    c = await _create_client(client, registered.headers)
    created = (await _create_proposal(client, registered.headers, c["id"])).json()
    resp = await client.get(f"{API}/proposals/{created['id']}", headers=registered.headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_get_proposal_cross_agency_404(client, registered, second_agency):
    c = await _create_client(client, registered.headers)
    created = (await _create_proposal(client, registered.headers, c["id"])).json()
    resp = await client.get(f"{API}/proposals/{created['id']}", headers=second_agency.headers)
    assert resp.status_code == 404


async def test_update_proposal(client, registered):
    c = await _create_client(client, registered.headers)
    created = (await _create_proposal(client, registered.headers, c["id"])).json()
    resp = await client.patch(
        f"{API}/proposals/{created['id']}",
        headers=registered.headers,
        json={"project_name": "Renamed Project", "status": "review"},
    )
    assert resp.status_code == 200
    assert resp.json()["project_name"] == "Renamed Project"
    assert resp.json()["status"] == "review"


async def test_delete_proposal(client, registered):
    c = await _create_client(client, registered.headers)
    created = (await _create_proposal(client, registered.headers, c["id"])).json()
    resp = await client.delete(f"{API}/proposals/{created['id']}", headers=registered.headers)
    assert resp.status_code == 204
    gone = await client.get(f"{API}/proposals/{created['id']}", headers=registered.headers)
    assert gone.status_code == 404


async def test_update_preferences_tracks_staleness(client, registered, db):
    """Changing a preference that maps to an already-completed phase marks
    that phase stale in pipeline_state."""
    c = await _create_client(client, registered.headers)
    created = (await _create_proposal(client, registered.headers, c["id"])).json()

    # mark narrative_review as a completed phase directly in the DB
    repo = ProposalRepository(db)
    await repo.update(
        created["id"],
        pipeline_state={"current_phase": "narrative_review", "phases_completed": ["narrative_review"]},
    )
    await db.commit()

    # letter_strategy maps to narrative_review -> it should become stale
    resp = await client.patch(
        f"{API}/proposals/{created['id']}/preferences",
        headers=registered.headers,
        json={"letter_strategy": "warm"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["preferences"]["letter_strategy"] == "warm"
    assert "narrative_review" in data["pipeline_state"]["stale_phases"]


async def test_update_can_clear_a_field_to_none(client, registered, db):
    """Regression test for the BaseRepository.update() None-drop fix — a text
    field that was set to a value can subsequently be cleared back to None."""
    c = await _create_client(client, registered.headers)
    created = (await _create_proposal(client, registered.headers, c["id"])).json()
    pid = created["id"]

    repo = ProposalRepository(db)
    await repo.update(pid, research="some research findings")
    await db.commit()
    assert (await repo.get_by_id(pid)).research == "some research findings"

    await repo.update(pid, research=None)
    await db.commit()
    assert (await repo.get_by_id(pid)).research is None

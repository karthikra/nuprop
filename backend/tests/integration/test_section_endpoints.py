"""Integration tests for section CRUD endpoints.

PATCH  /api/v1/proposals/{id}/sections/{section_type}
POST   /api/v1/proposals/{id}/sections/{section_type}/regenerate
POST   /api/v1/proposals/{id}/sections/{section_type}/refine
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from tests.conftest import API

_SAMPLE_SECTION = {
    "content": "Original content.",
    "assets": [],
    "included": True,
    "metadata": {},
}


async def _setup(http, headers):
    """Create a client + proposal via the API; return the proposal dict."""
    client_resp = await http.post(f"{API}/clients", headers=headers, json={"name": "Section Client"})
    assert client_resp.status_code == 201, client_resp.text
    c = client_resp.json()
    p_resp = await http.post(
        f"{API}/proposals",
        headers=headers,
        json={"client_id": c["id"], "project_name": "Section Project"},
    )
    assert p_resp.status_code == 201, p_resp.text
    return p_resp.json()


@pytest_asyncio.fixture
async def _proposal_with_section(client, registered, db):
    """Register an agency, create a client + proposal, set proposal.problem_statement
    to a known section payload. Return (proposal_dict, headers)."""
    p = await _setup(client, registered.headers)

    # Stamp a sample section directly via repo so endpoints have something to read.
    await ProposalRepository(db).update(p["id"], problem_statement=_SAMPLE_SECTION)
    await db.commit()

    # Re-fetch so the returned object reflects the stamped column.
    proposal = await ProposalRepository(db).get_by_id(p["id"])
    return proposal, registered.headers


async def test_patch_section_updates_content(client, _proposal_with_section):
    proposal, headers = _proposal_with_section
    r = await client.patch(
        f"{API}/proposals/{proposal.id}/sections/problem_statement",
        headers=headers,
        json={"content": "Edited by user."},
    )
    assert r.status_code == 200
    assert r.json()["content"] == "Edited by user."
    assert r.json()["included"] is True


async def test_patch_section_can_toggle_included(client, _proposal_with_section):
    proposal, headers = _proposal_with_section
    r = await client.patch(
        f"{API}/proposals/{proposal.id}/sections/problem_statement",
        headers=headers,
        json={"included": False},
    )
    assert r.status_code == 200
    assert r.json()["included"] is False


async def test_patch_unknown_section_type_returns_400(client, _proposal_with_section):
    proposal, headers = _proposal_with_section
    r = await client.patch(
        f"{API}/proposals/{proposal.id}/sections/not_a_section",
        headers=headers,
        json={"content": "x"},
    )
    assert r.status_code == 400


async def test_regenerate_calls_fact_generator_and_writes(
    client, _proposal_with_section, monkeypatch,
):
    proposal, headers = _proposal_with_section
    from app.services.ai import section_facts

    async def _fake_fact(section_type, **_):
        return {
            "content": f"REGENERATED {section_type}",
            "assets": [],
            "included": True,
            "metadata": {},
        }

    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)
    # Also patch the reference imported into the regeneration service.
    import app.services.sections.regeneration as regeneration
    monkeypatch.setattr(regeneration, "generate_fact_section", _fake_fact, raising=False)

    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/regenerate",
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["content"] == "REGENERATED problem_statement"


async def test_refine_passes_user_instructions(client, _proposal_with_section, monkeypatch):
    proposal, headers = _proposal_with_section
    from app.services.ai import section_facts

    captured: list[str] = []

    async def _capturing(section_type, **kwargs):
        captured.append(kwargs.get("refine_instructions") or "")
        return {"content": "refined", "assets": [], "included": True, "metadata": {}}

    monkeypatch.setattr(section_facts, "generate_fact_section", _capturing)
    import app.services.sections.regeneration as regeneration
    monkeypatch.setattr(regeneration, "generate_fact_section", _capturing, raising=False)

    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/refine",
        headers=headers,
        json={"instructions": "Make it shorter and more formal."},
    )
    assert r.status_code == 200
    assert captured == ["Make it shorter and more formal."]

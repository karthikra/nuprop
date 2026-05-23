from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.models.client import Client
from app.infrastructure.db.models.proposal import Proposal, ProposalStatus
from app.infrastructure.db.models.rate_card import RateCard
from app.services.pipeline_service import PipelineService
from tests.conftest import API


@pytest.fixture
async def _agency_with_proposal(_schema, db):
    """Minimal fixture: an agency with one proposal and no rate card."""
    agency = Agency(name="Acme Studio", slug="acme-studio")
    db.add(agency)
    await db.commit()
    client = Client(agency_id=agency.id, name="Horlicks", slug="horlicks", contacts=[])
    db.add(client)
    await db.commit()
    proposal = Proposal(
        agency_id=agency.id, client_id=client.id,
        project_name="Year campaign", status=ProposalStatus.DRAFT.value,
        brief={"deliverables": ["brand strategy", "monthly content"]},
        pipeline_state={},
    )
    db.add(proposal)
    await db.commit()
    return agency, proposal


@pytest.mark.asyncio
async def test_analyze_brief_writes_rate_card_gaps_when_rate_card_empty(
    _agency_with_proposal, db, monkeypatch,
):
    """When the rate card is empty and the analyzer identifies needed entries,
    analyze_brief writes them to proposal.rate_card_gaps."""
    agency, proposal = _agency_with_proposal

    from app.services.ai import brief_analyzer
    fake_result = MagicMock()
    fake_result.brief_complete = True
    fake_result.brief_data = {"deliverables": ["brand strategy"]}
    fake_result.response_text = "Brief analyzed"
    monkeypatch.setattr(brief_analyzer.BriefAnalyzer, "analyze",
                        AsyncMock(return_value=fake_result))

    from app.services.ai import rate_gap_analyzer
    monkeypatch.setattr(rate_gap_analyzer, "analyze_gaps", AsyncMock(return_value={
        "needed_roles": ["senior_strategist"],
        "needed_offerings": ["annual_retainer"],
    }))
    # Also patch the imported reference inside pipeline_service
    import app.services.pipeline_service as ps
    monkeypatch.setattr(ps, "analyze_gaps", AsyncMock(return_value={
        "needed_roles": ["senior_strategist"],
        "needed_offerings": ["annual_retainer"],
    }))

    svc = PipelineService(db, redis=AsyncMock())
    await svc.analyze_brief(proposal.id)

    await db.refresh(proposal)
    assert proposal.rate_card_gaps is not None
    assert proposal.rate_card_gaps["missing_roles"] == ["senior_strategist"]
    assert proposal.rate_card_gaps["missing_offerings"] == ["annual_retainer"]
    assert proposal.rate_card_gaps["needed_roles"] == ["senior_strategist"]
    assert proposal.rate_card_gaps["needed_offerings"] == ["annual_retainer"]


@pytest.mark.asyncio
async def test_analyze_brief_no_gaps_when_rate_card_covers_everything(
    _agency_with_proposal, db, monkeypatch,
):
    """When the rate card already contains all needed entries, rate_card_gaps stays None."""
    agency, proposal = _agency_with_proposal
    rate_card = RateCard(
        agency_id=agency.id, version="v1", is_active=True,
        offerings={"annual_retainer": {"name": "Annual Retainer", "base_price": 100}},
        hourly_rates={"senior_strategist": 4500},
    )
    db.add(rate_card)
    await db.commit()

    from app.services.ai import brief_analyzer
    fake_result = MagicMock()
    fake_result.brief_complete = True
    fake_result.brief_data = {"deliverables": ["strategy"]}
    fake_result.response_text = "ok"
    monkeypatch.setattr(brief_analyzer.BriefAnalyzer, "analyze",
                        AsyncMock(return_value=fake_result))

    import app.services.pipeline_service as ps
    monkeypatch.setattr(ps, "analyze_gaps", AsyncMock(return_value={
        "needed_roles": ["senior_strategist"],
        "needed_offerings": ["annual_retainer"],
    }))

    svc = PipelineService(db, redis=AsyncMock())
    await svc.analyze_brief(proposal.id)

    await db.refresh(proposal)
    assert proposal.rate_card_gaps is None


@pytest.mark.asyncio
async def test_template_gate_does_not_enqueue_research_when_gaps_exist(
    _agency_with_proposal, db, monkeypatch,
):
    """Approving the template gate must NOT enqueue run_research if
    proposal.rate_card_gaps is set."""
    from app.viewmodels.chat_viewmodel import ChatViewModel

    agency, proposal = _agency_with_proposal
    # Simulate that analyze_brief earlier wrote gaps
    proposal.rate_card_gaps = {
        "missing_roles": ["senior_strategist"], "missing_offerings": [],
        "needed_roles": ["senior_strategist"], "needed_offerings": [],
    }
    proposal.pipeline_state = {}
    await db.commit()

    enqueued: list[str] = []

    async def _fake_enqueue(self, job_name, proposal_id, idempotency_key=None):
        enqueued.append(job_name)

    monkeypatch.setattr(ChatViewModel, "_enqueue", _fake_enqueue)

    vm = ChatViewModel(request=MagicMock(), db=db)
    msg = await vm.approve_gate(proposal.id, agency.id, "template", {"template_key": "t1"})

    assert msg is not None
    assert enqueued == []  # no enqueue while gaps exist
    await db.refresh(proposal)
    assert proposal.pipeline_state.get("current_phase") == "rate_card_gaps"


@pytest.mark.asyncio
async def test_get_proposal_includes_rate_card_gaps(client, registered):
    """GET /api/v1/proposals/{id} must include rate_card_gaps in the response body.

    Regression guard for the ProposalResponse schema omission — FastAPI's
    response_model silently strips undeclared fields, so this test confirms
    the field round-trips correctly.
    """
    # Create a client + proposal via the API
    c_resp = await client.post(
        f"{API}/clients", headers=registered.headers, json={"name": "Gap Test Client"}
    )
    assert c_resp.status_code == 201
    c_data = c_resp.json()

    p_resp = await client.post(
        f"{API}/proposals",
        headers=registered.headers,
        json={"client_id": c_data["id"], "project_name": "Gap Round-Trip Test"},
    )
    assert p_resp.status_code == 201
    proposal_id = p_resp.json()["id"]

    # Directly write rate_card_gaps into the DB (simulating analyze_brief output)
    from app.infrastructure.db.database import async_session_factory
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository

    known_gaps = {
        "missing_roles": ["senior_strategist"],
        "missing_offerings": ["annual_retainer"],
        "needed_roles": ["senior_strategist"],
        "needed_offerings": ["annual_retainer"],
    }
    async with async_session_factory() as session:
        repo = ProposalRepository(session)
        await repo.update(proposal_id, rate_card_gaps=known_gaps)
        await session.commit()

    # Fetch via the API and assert the field is present
    get_resp = await client.get(
        f"{API}/proposals/{proposal_id}", headers=registered.headers
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "rate_card_gaps" in data, "rate_card_gaps must be present in ProposalResponse"
    assert data["rate_card_gaps"]["missing_roles"] == ["senior_strategist"]
    assert data["rate_card_gaps"]["missing_offerings"] == ["annual_retainer"]

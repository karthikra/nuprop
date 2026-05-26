from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.models.client import Client
from app.infrastructure.db.models.proposal import Proposal, ProposalStatus
from app.services.pipeline_service import PipelineService
from app.services.sections import FACT_SECTIONS, SYNTHESIS_SECTIONS


@pytest.fixture
async def _proposal_ready_for_sections(_schema, db):
    """Agency + client + proposal with brief committed and cost_model populated —
    the state immediately after the user approves the cost-model gate."""
    agency = Agency(name="Studio X", slug="studio-x")
    db.add(agency)
    await db.commit()
    client = Client(agency_id=agency.id, name="Acme", slug="acme", contacts=[])
    db.add(client)
    await db.commit()
    proposal = Proposal(
        agency_id=agency.id, client_id=client.id,
        project_name="Annual campaign",
        status=ProposalStatus.GENERATING.value,
        brief={
            "client": {"name": "Acme"},
            "project": {"name": "Annual campaign", "deliverables": [
                {"category": "strategy", "name": "Brand strategy"},
            ]},
        },
        cost_model={"total": 1500000, "line_items": [
            {"name": "Strategy", "amount": 1500000},
        ]},
        research="Brief research summary.",
        benchmarks="Market benchmark summary.",
    )
    db.add(proposal)
    await db.commit()
    return agency, proposal


@pytest.mark.asyncio
async def test_generate_sections_populates_all_seven_fact_columns(
    _proposal_ready_for_sections, db, monkeypatch,
):
    """After Pass 1 runs, all seven fact columns are populated with section payloads."""
    agency, proposal = _proposal_ready_for_sections

    from app.services.ai import section_facts, section_synthesis

    async def _fake_fact(section_type, **_):
        return {"content": f"FACT {section_type}", "assets": [], "included": True, "metadata": {}}

    async def _fake_synth(section_type, **_):
        return {"content": f"SYNTH {section_type}", "assets": [], "included": True, "metadata": {}}

    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)
    monkeypatch.setattr(section_synthesis, "generate_synthesis_section", _fake_synth)
    # Also patch the pipeline_service-imported references
    import app.services.pipeline_service as ps
    monkeypatch.setattr(ps, "generate_fact_section", _fake_fact)
    monkeypatch.setattr(ps, "generate_synthesis_section", _fake_synth)

    svc = PipelineService(db, redis=AsyncMock())
    await svc.generate_sections(proposal.id)

    await db.refresh(proposal)
    for section_type in FACT_SECTIONS:
        column_value = getattr(proposal, section_type)
        assert column_value is not None, f"{section_type} should be populated"
        assert column_value["content"] == f"FACT {section_type}"
    for section_type in SYNTHESIS_SECTIONS:
        column_value = getattr(proposal, section_type)
        assert column_value is not None, f"{section_type} should be populated"
        assert column_value["content"] == f"SYNTH {section_type}"


@pytest.mark.asyncio
async def test_generate_sections_skips_sections_not_in_template_defaults(
    _proposal_ready_for_sections, db, monkeypatch,
):
    """When the proposal's template config lists default_sections, only those are generated."""
    agency, proposal = _proposal_ready_for_sections

    proposal.template_id = "minimal-template"
    await db.commit()

    async def _fake_template_config(_self, _proposal):
        return {"default_sections": ["problem_statement", "pricing", "executive_summary"]}
    monkeypatch.setattr(PipelineService, "_load_template_config", _fake_template_config)

    from app.services.ai import section_facts, section_synthesis
    fact_calls: list[str] = []
    synth_calls: list[str] = []

    async def _fake_fact(section_type, **_):
        fact_calls.append(section_type)
        return {"content": "x", "assets": [], "included": True, "metadata": {}}

    async def _fake_synth(section_type, **_):
        synth_calls.append(section_type)
        return {"content": "x", "assets": [], "included": True, "metadata": {}}

    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)
    monkeypatch.setattr(section_synthesis, "generate_synthesis_section", _fake_synth)
    import app.services.pipeline_service as ps
    monkeypatch.setattr(ps, "generate_fact_section", _fake_fact)
    monkeypatch.setattr(ps, "generate_synthesis_section", _fake_synth)

    svc = PipelineService(db, redis=AsyncMock())
    await svc.generate_sections(proposal.id)

    assert set(fact_calls) == {"problem_statement", "pricing"}
    assert set(synth_calls) == {"executive_summary"}

    await db.refresh(proposal)
    assert proposal.problem_statement is not None
    assert proposal.pricing is not None
    assert proposal.executive_summary is not None
    assert proposal.cover_page is None
    assert proposal.proposed_solution is None
    assert proposal.scope_of_work is None
    assert proposal.timeline is None
    assert proposal.qualifications is None
    assert proposal.terms_and_conditions is None

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.models.client import Client
from app.infrastructure.db.models.proposal import Proposal, ProposalStatus
from app.viewmodels.chat_viewmodel import ChatViewModel


@pytest.fixture
async def _proposal_at_cost_model_gate(_schema, db):
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
        brief={"client": {"name": "Acme"}},
        cost_model={"total": 1500000},
        pipeline_state={"current_phase": "cost_model_review", "phases_completed": []},
    )
    db.add(proposal)
    await db.commit()
    return agency, proposal


@pytest.mark.asyncio
async def test_approving_cost_model_gate_enqueues_generate_sections_not_narrative(
    _proposal_at_cost_model_gate, db, monkeypatch,
):
    """The narrative gate is gone. cost_model approval enqueues generate_sections directly."""
    agency, proposal = _proposal_at_cost_model_gate

    enqueued: list[str] = []

    async def _fake_enqueue(self, job_name, proposal_id, idempotency_key=None):
        enqueued.append(job_name)

    monkeypatch.setattr(ChatViewModel, "_enqueue", _fake_enqueue)

    vm = ChatViewModel(request=MagicMock(), db=db)
    msg = await vm.approve_gate(proposal.id, agency.id, "cost_model", {})

    assert msg is not None
    assert enqueued == ["generate_sections"]


@pytest.mark.asyncio
async def test_narrative_gate_no_longer_exists(
    _proposal_at_cost_model_gate, db,
):
    """Approving a 'narrative' gate now returns None with an error set on the vm (unknown gate)."""
    agency, proposal = _proposal_at_cost_model_gate

    vm = ChatViewModel(request=MagicMock(), db=db)
    result = await vm.approve_gate(proposal.id, agency.id, "narrative", {})

    assert result is None
    assert vm.error is not None
    assert "narrative" in vm.error.lower() or "unknown" in vm.error.lower()

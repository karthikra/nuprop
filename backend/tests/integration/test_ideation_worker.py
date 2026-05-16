"""Tests for the run_ideation ARQ task wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.workers import pipeline as worker


async def _make_proposal(db):
    agency = await AgencyRepository(db).create(name="IW Agency", slug="iw-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="IW Project",
        brief={},
        pipeline_state={"current_phase": "brief", "phases_completed": []},
    )
    await db.commit()
    return proposal


def _ctx():
    return {"redis": AsyncMock(), "job_try": 1}


async def test_run_ideation_task_does_not_touch_pipeline_state(db, monkeypatch):
    proposal = await _make_proposal(db)
    pid = str(proposal.id)
    pipeline_state_before = dict(proposal.pipeline_state)

    # Stub IdeationService so we don't need real Bedrock.
    from app.services import ideation_service as ide_mod

    async def fake_run_ideation(self, proposal_id):  # noqa: ARG001
        return None

    monkeypatch.setattr(ide_mod.IdeationService, "run_ideation", fake_run_ideation)

    await worker.run_ideation(_ctx(), pid)

    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
    assert refetched.pipeline_state == pipeline_state_before, (
        "ideation must not write job_status or anything else into pipeline_state"
    )


async def test_run_ideation_task_records_error_message_on_failure(db, monkeypatch):
    proposal = await _make_proposal(db)
    pid = str(proposal.id)
    pipeline_state_before = dict(proposal.pipeline_state)

    from app.services import ideation_service as ide_mod

    async def boom(self, proposal_id):  # noqa: ARG001
        raise RuntimeError("bedrock unreachable")

    monkeypatch.setattr(ide_mod.IdeationService, "run_ideation", boom)

    # Spy on the publish helper to verify the pipeline_error WS event is sent.
    sent = []
    async def _spy(redis, pid_arg, payload):
        sent.append((pid_arg, payload))

    monkeypatch.setattr("app.workers.pipeline.publish", _spy)

    await worker.run_ideation(_ctx(), pid)  # must NOT raise

    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(
            pid, channel="ideation",
        )
        error_msgs = [m for m in msgs if (m.extra_data or {}).get("kind") == "error"]
        assert error_msgs, "expected an error chat message on the ideation channel"
        assert error_msgs[0].role == "system"
        assert "Couldn't reach Bedrock" in error_msgs[0].content
        assert error_msgs[0].extra_data["error"] == "bedrock unreachable"

        refetched = await ProposalRepository(fresh).get_by_id(pid)
    assert refetched.pipeline_state == pipeline_state_before

    # Two publishes expected: new_message for the error row, then pipeline_error.
    assert len(sent) == 2, f"expected 2 publish calls, got {len(sent)}: {sent}"
    first_type = sent[0][1]["type"]
    second_type = sent[1][1]["type"]
    assert {first_type, second_type} == {"new_message", "pipeline_error"}

    # The new_message carries the error row.
    new_msg_payload = next(p for _, p in sent if p["type"] == "new_message")
    assert new_msg_payload["message"]["channel"] == "ideation"
    assert new_msg_payload["message"]["role"] == "system"
    assert new_msg_payload["message"]["extra_data"]["kind"] == "error"

    # pipeline_error is also present for observability.
    pipeline_err_payload = next(p for _, p in sent if p["type"] == "pipeline_error")
    assert pipeline_err_payload == {"type": "pipeline_error", "phase": "ideation", "error": "bedrock unreachable"}

"""Regression test for the proposal-field persistence bug.

Previously the whole pipeline ran in one request transaction committed only at
request end, so a phase's writes were not visible to a concurrent reader until
the entire request finished. Now each phase commits in its own session before it
broadcasts — proven here by reading the written field from a *separate* session.

The original test mocked ``ResearchAgent.research_client`` (the agent-level path),
which the streaming rewrite of ``run_research`` no longer calls. This version mocks
the new path: the Haiku planner + the Opus streaming call on ``ai.client.messages.stream``.
The structural invariant is identical: the ``research_findings`` broadcast (a
``new_message`` event) must follow the ``proposal.research`` commit.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.pipeline_service import PipelineService


def _start(content_block):
    return SimpleNamespace(type="content_block_start", content_block=content_block)


def _delta(text):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _stop(content_block):
    return SimpleNamespace(type="content_block_stop", content_block=content_block)


class _MockStreamContext:
    """Stands in for the async context manager returned by messages.stream(...)."""

    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    def __aiter__(self):
        async def _gen():
            for ev in self._events:
                yield ev
        return _gen()


async def test_phase_commits_before_it_would_broadcast(db, monkeypatch):
    agency = await AgencyRepository(db).create(name="P Agency", slug="p-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="P",
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    await db.commit()
    pid = proposal.id

    research_text = "Acme rebranded in 2024. Committed before broadcast."

    # Mock the Haiku planner.
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": ["Acme rebrand"], "rationale": "..."}),
    )

    # Mock synthesize_research — returns the body that becomes proposal.research.
    # (Was streaming + tool-use; now Serper + non-streaming synth. See § 5e.)
    async def _synth(*, queries, system_prompt, user_message, on_event, **_):
        await on_event({"type": "search", "query": queries[0] if queries else "x",
                        "ts": "2026-01-01T00:00:00+00:00"})
        return research_text, [], []

    monkeypatch.setattr("app.services.pipeline_service.synthesize_research", _synth)

    # Record every emit with whether the committed research write was visible
    # at that point. The invariant: any broadcast of the *research_findings*
    # message must follow the commit of ``proposal.research`` (the bug was that
    # they did not). Plan / activity-log emits legitimately fire before the
    # research field is written.
    observations: list[tuple[dict, bool]] = []

    async def _emit_spy(redis, proposal_id, payload):  # noqa: ANN001
        async with async_session_factory() as observer:
            row = await ProposalRepository(observer).get_by_id(proposal_id)
            committed = row is not None and row.research == research_text
            observations.append((payload, committed))

    monkeypatch.setattr("app.services.pipeline_service.publish", _emit_spy, raising=False)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(pid)

    assert observations, "run_research should emit at least one WS event"
    # The findings broadcast must see the committed write.
    findings_emits = [
        committed for payload, committed in observations
        if payload.get("type") == "new_message"
        and payload.get("message", {}).get("message_type") == "research_findings"
    ]
    assert findings_emits, "expected a 'research_findings' new_message broadcast from run_research"
    assert all(findings_emits), (
        "every research_findings broadcast must follow the proposal.research commit"
    )

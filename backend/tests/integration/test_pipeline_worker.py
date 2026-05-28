"""Tests for the ARQ pipeline task functions.

These exercise the worker-level ``_run_phase`` wrapper (job_status bookkeeping,
chained-enqueue on success, terminal-failure handling) against the streaming
``run_research`` path. We mock the planner + ``ai.client.messages.stream`` —
the same shape ``test_research_transparency.py`` uses — rather than the
defunct ``ResearchAgent.research_client`` agent method.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.workers import pipeline as worker


def _ctx(job_try=1):
    return {"redis": AsyncMock(), "job_try": job_try}


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


def _patch_research_pipeline(monkeypatch, *, body: str = "", raises: Exception | None = None):
    """Patch the Haiku planner + synthesize_research so run_research runs without
    hitting Bedrock or Serper. (Was: streaming + tool-use; now: synthesize_research.)"""
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )

    async def _synth(*, on_event, **_):
        await on_event({"type": "search", "query": "x", "ts": "2026-01-01T00:00:00+00:00"})
        if raises is not None:
            raise raises
        return body, [], []

    monkeypatch.setattr("app.services.pipeline_service.synthesize_research", _synth)


async def test_run_research_task_sets_job_status_and_enqueues_next(db, monkeypatch, make_proposal_db):
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    pid = str(proposal.id)

    body_text = "Acme research summary."
    _patch_research_pipeline(monkeypatch, body=body_text)

    ctx = _ctx()
    await worker.run_research(ctx, pid)

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.pipeline_state["job_status"]["state"] == "complete"
    ctx["redis"].enqueue_job.assert_awaited()  # chained run_benchmarks
    assert ctx["redis"].enqueue_job.await_args.args[0] == "run_benchmarks"


async def test_task_marks_failed_and_emits_pipeline_error_on_exception(db, monkeypatch, make_proposal_db):
    """Any phase exception is terminal: state -> 'failed' + pipeline_error broadcast.

    ARQ does NOT auto-retry on a bare ``raise`` (that requires the explicit
    ``arq.jobs.Retry`` exception). The smoke test confirmed this; the worker
    records every failure as terminal so the user can re-attempt via
    POST /chat/{id}/retry.
    """
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    pid = str(proposal.id)

    _patch_research_pipeline(monkeypatch, raises=RuntimeError("LLM down"))

    ctx = _ctx()
    await worker.run_research(ctx, pid)  # must NOT raise

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.pipeline_state["job_status"]["state"] == "failed"
        assert "LLM down" in refetched.pipeline_state["job_status"]["error"]

    # The pipeline_error broadcast went to Redis
    calls = ctx["redis"].publish.await_args_list
    assert calls, "expected a publish() call for the pipeline_error event"
    # Subsequent phase should NOT be enqueued on failure
    ctx["redis"].enqueue_job.assert_not_called()


async def test_chain_enqueue_clears_stale_result_key_before_enqueueing_next_phase(
    db, monkeypatch, make_proposal_db
):
    """Regression for the worker chain (run_research -> run_benchmarks ->
    build_cost_model). A failed prior run on the SAME _job_id leaves a
    poisoned arq:result key (24h TTL). The chain MUST DEL it before
    enqueueing the next phase so re-runs aren't silently swallowed."""
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    pid = str(proposal.id)

    _patch_research_pipeline(monkeypatch, body="Acme research summary.")

    ctx = _ctx()
    await worker.run_research(ctx, pid)

    redis = ctx["redis"]
    # The next phase's result-cache key is DEL'd before the chained enqueue.
    redis.delete.assert_awaited_once_with(f"arq:result:{pid}:run_benchmarks")
    redis.enqueue_job.assert_awaited_once()
    assert redis.enqueue_job.await_args.args[0] == "run_benchmarks"


async def test_chain_enqueue_clears_stale_result_key_for_benchmarks_to_cost_model_hop(
    db, monkeypatch, make_proposal_db
):
    """Same regression as above, but for the SECOND chain hop
    (run_benchmarks -> build_cost_model — the second entry in ``_NEXT_PHASE``).
    Running ``run_benchmarks`` must DEL the poisoned
    ``arq:result:<pid>:build_cost_model`` key before enqueueing build_cost_model
    so a re-run on the same _job_id isn't silently swallowed."""
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    pid = str(proposal.id)

    # Mock the PipelineService.run_benchmarks method to succeed without hitting
    # Bedrock — mirrors how the run_research hop mocks its phase internals.
    monkeypatch.setattr(
        "app.services.pipeline_service.PipelineService.run_benchmarks",
        AsyncMock(return_value=None),
    )

    ctx = _ctx()
    await worker.run_benchmarks(ctx, pid)

    redis = ctx["redis"]
    # The next phase's result-cache key is DEL'd before the chained enqueue.
    redis.delete.assert_awaited_once_with(f"arq:result:{pid}:build_cost_model")
    redis.enqueue_job.assert_awaited_once()
    assert redis.enqueue_job.await_args.args[0] == "build_cost_model"


async def test_run_phase_broadcasts_job_status_running_then_complete(db, make_proposal_db, monkeypatch):
    import json
    from datetime import datetime

    from app.services.pipeline_service import PipelineService
    from app.workers.pipeline import _run_phase
    monkeypatch.setattr(PipelineService, "run_research", AsyncMock(return_value=None))
    agency, client, proposal = await make_proposal_db()
    redis = AsyncMock()
    await _run_phase({"redis": redis}, "run_research", str(proposal.id))
    states = []
    payloads_by_state: dict[str, dict] = {}
    for call in redis.publish.await_args_list:
        env = json.loads(call.args[1])
        payload = env["payload"]
        if payload.get("type") == "job_status":
            states.append(payload["state"])
            payloads_by_state[payload["state"]] = payload
    assert "running" in states
    assert "complete" in states
    # The timer anchor must be present and ISO-parseable on the live payloads —
    # guards against a future change silently dropping updated_at.
    for state in ("running", "complete"):
        updated_at = payloads_by_state[state].get("updated_at")
        assert updated_at, f"{state} job_status missing updated_at"
        datetime.fromisoformat(updated_at)  # raises if not ISO


async def test_run_phase_broadcasts_job_status_failed_on_error(db, make_proposal_db, monkeypatch):
    import json

    from app.services.pipeline_service import PipelineService
    from app.workers.pipeline import _run_phase
    monkeypatch.setattr(PipelineService, "run_research", AsyncMock(side_effect=RuntimeError("boom")))
    agency, client, proposal = await make_proposal_db()
    redis = AsyncMock()
    await _run_phase({"redis": redis}, "run_research", str(proposal.id))
    failed = []
    for call in redis.publish.await_args_list:
        env = json.loads(call.args[1])
        if env["payload"].get("type") == "job_status" and env["payload"]["state"] == "failed":
            failed.append(env["payload"])
    assert failed and failed[0]["error"]

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

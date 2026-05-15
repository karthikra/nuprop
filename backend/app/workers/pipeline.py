"""ARQ pipeline tasks — one durable job per proposal-pipeline phase.

Each task opens its own AsyncSession, runs a PipelineService phase (which commits
before it broadcasts), records job_status on the proposal, and chains the next
phase. Run the worker process with: ``arq app.workers.pipeline.WorkerSettings``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.queue.events import publish
from app.infrastructure.queue.redis import get_redis_settings
from app.services.pipeline_service import PipelineService

logger = logging.getLogger(__name__)

ARQ_MAX_TRIES = get_settings().ARQ_MAX_TRIES

# phase -> the job that runs automatically after it (chaining within a gate)
_NEXT_PHASE = {
    "run_research": "run_benchmarks",
    "run_benchmarks": "build_cost_model",
}


async def _set_job_status(session, proposal_id, phase, state, error=None) -> None:
    repo = ProposalRepository(session)
    proposal = await repo.get_by_id(proposal_id)
    if proposal is None:
        return
    pipeline = proposal.pipeline_state.copy()
    pipeline["job_status"] = {
        "phase": phase,
        "state": state,
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await repo.update(proposal_id, pipeline_state=pipeline)
    await session.commit()


async def _run_phase(ctx: dict, phase: str, proposal_id: str) -> None:
    """Shared task body: status bookkeeping + retry-to-failed handling."""
    async with async_session_factory() as session:
        await _set_job_status(session, proposal_id, phase, "running")

    try:
        async with async_session_factory() as session:
            svc = PipelineService(session, ctx["redis"])
            await getattr(svc, phase)(proposal_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline phase %s failed for %s", phase, proposal_id)
        if ctx["job_try"] >= ARQ_MAX_TRIES:
            async with async_session_factory() as session:
                await _set_job_status(session, proposal_id, phase, "failed", str(exc))
            await publish(ctx["redis"], proposal_id, {
                "type": "pipeline_error", "phase": phase, "error": str(exc),
            })
            return  # swallow on the final try — job is "done" (failed)
        raise  # let ARQ retry

    async with async_session_factory() as session:
        await _set_job_status(session, proposal_id, phase, "complete")

    next_phase = _NEXT_PHASE.get(phase)
    if next_phase:
        await ctx["redis"].enqueue_job(
            next_phase, proposal_id, _job_id=f"{proposal_id}:{next_phase}"
        )


async def analyze_brief(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "analyze_brief", proposal_id)


async def run_research(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "run_research", proposal_id)


async def run_benchmarks(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "run_benchmarks", proposal_id)


async def build_cost_model(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "build_cost_model", proposal_id)


async def generate_narrative(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "generate_narrative", proposal_id)


async def generate_outputs(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "generate_outputs", proposal_id)


class WorkerSettings:
    functions = [
        analyze_brief, run_research, run_benchmarks,
        build_cost_model, generate_narrative, generate_outputs,
    ]
    redis_settings = get_redis_settings()
    max_tries = ARQ_MAX_TRIES

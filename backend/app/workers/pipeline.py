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
from app.infrastructure.queue.enqueue import enqueue_phase_job
from app.infrastructure.queue.events import publish
from app.infrastructure.queue.redis import get_redis_settings
from app.services.pipeline_service import PipelineService
from app.workers.enrichment import enrich_context_from_emails

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
    """Shared task body: status bookkeeping + terminal-on-error handling.

    ARQ treats any uncaught exception as terminal (it does NOT auto-retry on a
    bare ``raise`` — that requires ``raise arq.jobs.Retry()`` explicitly). So
    every failure here is recorded as ``state="failed"`` with a
    ``pipeline_error`` WS broadcast; re-attempts happen via the
    ``POST /chat/{id}/retry`` endpoint, which re-enqueues the phase.
    """
    async with async_session_factory() as session:
        await _set_job_status(session, proposal_id, phase, "running")

    try:
        async with async_session_factory() as session:
            svc = PipelineService(session, ctx["redis"])
            await getattr(svc, phase)(proposal_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline phase %s failed for %s", phase, proposal_id)
        async with async_session_factory() as session:
            await _set_job_status(session, proposal_id, phase, "failed", str(exc))
        await publish(ctx["redis"], proposal_id, {
            "type": "pipeline_error", "phase": phase, "error": str(exc),
        })
        return  # don't re-raise — terminal failure is recorded; user retries via /retry

    async with async_session_factory() as session:
        await _set_job_status(session, proposal_id, phase, "complete")

    next_phase = _NEXT_PHASE.get(phase)
    if next_phase:
        await enqueue_phase_job(
            ctx["redis"],
            job_name=next_phase,
            proposal_id=str(proposal_id),
        )


async def analyze_brief(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "analyze_brief", proposal_id)


async def run_research(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "run_research", proposal_id)


async def run_benchmarks(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "run_benchmarks", proposal_id)


async def build_cost_model(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "build_cost_model", proposal_id)


async def generate_sections(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "generate_sections", proposal_id)


async def _run_ideation_phase(ctx: dict, proposal_id: str) -> None:
    """Run an ideation turn. Isolated from the main pipeline:

    * Does NOT update ``proposal.pipeline_state`` — ideation has no job_status.
    * On failure, writes a single error message to the ideation channel and
      returns cleanly (ARQ marks the job done). The user re-prompts to retry.
    """
    from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
    from app.services.ideation_service import IdeationService

    try:
        async with async_session_factory() as session:
            await IdeationService(session, ctx["redis"]).run_ideation(proposal_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ideation phase failed for %s", proposal_id)
        from app.domain.schemas.chat_schemas import ChatMessageResponse
        async with async_session_factory() as session:
            error_msg = await ChatMessageRepository(session).create(
                proposal_id=proposal_id,
                role="system",
                message_type="text",
                content="Couldn't reach Bedrock. Send another message to try again.",
                extra_data={"kind": "error", "error": str(exc)},
                phase="ideation",
                channel="ideation",
            )
            await session.commit()
            # Broadcast the error row as a regular new_message so the drawer's
            # message-list rendering picks it up via the existing addMessage path.
            await publish(ctx["redis"], proposal_id, {
                "type": "new_message",
                "message": ChatMessageResponse.model_validate(error_msg).model_dump(mode="json"),
            })
        # Keep the pipeline_error broadcast for observability.
        await publish(ctx["redis"], proposal_id, {
            "type": "pipeline_error",
            "phase": "ideation",
            "error": str(exc),
        })


async def run_ideation(ctx: dict, proposal_id: str) -> None:
    # Thin wrapper mirroring the main pipeline's pattern (function name == ARQ task name).
    # Actual logic lives in `_run_ideation_phase` so the try/except boundary is
    # visually parallel to `_run_phase` for the main pipeline tasks.
    await _run_ideation_phase(ctx, proposal_id)


class WorkerSettings:
    functions = [
        analyze_brief, run_research, run_benchmarks,
        build_cost_model, generate_sections,
        run_ideation,
        enrich_context_from_emails,
    ]
    redis_settings = get_redis_settings()
    max_tries = ARQ_MAX_TRIES

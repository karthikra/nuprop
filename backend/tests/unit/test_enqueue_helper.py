"""Unit tests for the shared `enqueue_phase_job` helper.

The helper exists because ARQ uses ``_job_id`` as a 24h result-cache key.
A failed prior run leaves a poisoned key, and subsequent re-enqueues
silently no-op until the TTL expires. The fix is to DEL the result key
before every enqueue. This was previously inlined in chat_viewmodel; this
test pins the contract for the extracted helper.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.queue.enqueue import enqueue_phase_job


@pytest.mark.asyncio
async def test_deletes_result_key_then_enqueues():
    pool = AsyncMock()
    await enqueue_phase_job(
        pool, job_name="run_research", proposal_id="abc-123",
    )
    pool.delete.assert_awaited_once_with("arq:result:abc-123:run_research")
    pool.enqueue_job.assert_awaited_once_with(
        "run_research", "abc-123", _job_id="abc-123:run_research",
    )


@pytest.mark.asyncio
async def test_delete_failure_does_not_block_enqueue():
    """A transient Redis hiccup on DEL must not poison the actual enqueue.
    Mirrors the inline behaviour from chat_viewmodel._enqueue."""
    pool = AsyncMock()
    pool.delete.side_effect = ConnectionError("redis transient")
    await enqueue_phase_job(
        pool, job_name="run_research", proposal_id="abc-123",
    )
    pool.enqueue_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_idempotency_key_makes_job_id_unique():
    """For per-turn enqueues (analyze_brief on each chat send) the caller
    can pass an idempotency_key — the resulting _job_id is unique so the
    result-key DEL is a harmless no-op."""
    pool = AsyncMock()
    await enqueue_phase_job(
        pool, job_name="analyze_brief", proposal_id="abc-123",
        idempotency_key="turn-7",
    )
    pool.delete.assert_awaited_once_with("arq:result:abc-123:analyze_brief:turn-7")
    pool.enqueue_job.assert_awaited_once_with(
        "analyze_brief", "abc-123", _job_id="abc-123:analyze_brief:turn-7",
    )

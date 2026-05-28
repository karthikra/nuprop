"""Shared ARQ enqueue helper that defangs the result-cache retry trap.

ARQ uses ``_job_id`` for two flavours of deduplication:

* **In-flight dedup** — if a job with the same ``_job_id`` is currently
  queued or being processed, ARQ silently drops the duplicate. This is
  the property we want: protects against double-click on Approve, double
  webhook delivery, etc.
* **Result-cache dedup** — once a job finishes (success OR failure), ARQ
  stores its result under ``arq:result:<job_id>`` for 24h. While that
  key exists, every subsequent ``enqueue_job`` for the same ``_job_id``
  silently no-ops. **This breaks the retry-after-failure flow** — a
  failed gate-approval leaves a poisoned result key, and every later
  "retry" silently no-ops for the TTL window.

The fix: explicitly ``DEL`` the result key before enqueueing. In-flight
dedup still works (queue/in-progress keys are not touched).

Callers that need a fresh run per invocation (e.g. ``analyze_brief`` per
chat turn) pass an ``idempotency_key`` so the resulting ``_job_id`` is
unique; the DEL is a no-op for those since the key never existed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def enqueue_phase_job(
    pool: Any,
    *,
    job_name: str,
    proposal_id: str,
    idempotency_key: str | None = None,
) -> None:
    """DEL the result-cache key, then enqueue the job.

    ``pool`` is an ARQ pool (``ArqRedis``) — duck-typed here so the helper
    is trivially mockable in tests.
    """
    suffix = f":{idempotency_key}" if idempotency_key else ""
    job_id = f"{proposal_id}:{job_name}{suffix}"
    try:
        await pool.delete(f"arq:result:{job_id}")
    except Exception:  # noqa: BLE001 — DEL must not poison the enqueue
        logger.debug(
            "redis DEL failed before enqueue (job_id=%s); continuing", job_id,
        )
    await pool.enqueue_job(job_name, str(proposal_id), _job_id=job_id)

"""Streaming-event handling for the run_research / run_benchmarks phases.

Two responsibilities split into well-named units:

- :class:`ActivityFlusher` — batched-flush primitive for a single
  ``*_activity_log`` chat message. Accumulates ``ActivityEvent`` rows,
  persists them in batches, commits, and publishes ``message_updated`` WS
  events.

- :func:`process_stream` — pure(ish) async function that consumes an
  Anthropic SDK message-stream and converts it into ``ActivityEvent`` calls
  to a provided callback while accumulating the final body, citation list,
  and span list. (Added in the next task.)
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.queue.events import publish_message_updated

logger = logging.getLogger(__name__)

# Flush triggers — chosen to feel "live" without over-committing.
_FLUSH_MAX_EVENTS: int = 5
_FLUSH_MAX_INTERVAL_S: float = 0.75


class ActivityFlusher:
    """Batched-flush helper for an activity-log chat message.

    Each :meth:`append` adds an ``ActivityEvent`` dict; a flush (DB UPDATE +
    commit + WS publish) fires when either ``_FLUSH_MAX_EVENTS`` is reached
    or ``_FLUSH_MAX_INTERVAL_S`` seconds have elapsed since the last flush.
    Call :meth:`flush` directly at end-of-stream with ``final_status`` set
    to mark the log as complete or failed.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        msg_repo: ChatMessageRepository,
        redis,
        log_msg_id,
        proposal_id,
        phase: str,
    ) -> None:
        self.session = session
        self.msg_repo = msg_repo
        self.redis = redis
        self.log_msg_id = log_msg_id
        self.proposal_id = proposal_id
        self.phase = phase
        self._all_events: list[dict[str, Any]] = []
        self._pending_count: int = 0
        self._last_flush_ts: float = monotonic()

    async def append(self, event: dict[str, Any]) -> None:
        self._all_events.append(event)
        self._pending_count += 1
        if (
            self._pending_count >= _FLUSH_MAX_EVENTS
            or (monotonic() - self._last_flush_ts) >= _FLUSH_MAX_INTERVAL_S
        ):
            await self.flush()

    async def flush(
        self,
        *,
        final_status: str | None = None,
        error: str | None = None,
    ) -> None:
        """Persist current state + publish a message_updated event.

        When ``final_status`` is provided (``"complete"`` or ``"failed"``)
        the activity-log message is marked terminal in its ``extra_data``;
        otherwise it stays ``"running"``.
        """
        # Short-circuit: nothing to do if no events accumulated AND we're not
        # being explicitly asked to set a terminal status.
        if self._pending_count == 0 and final_status is None:
            return

        extra: dict[str, Any] = {
            "phase": self.phase,
            "status": final_status or "running",
            "events": list(self._all_events),
        }
        if error:
            extra["error"] = error

        await self.msg_repo.update(self.log_msg_id, extra_data=extra)
        await self.session.commit()
        refreshed = await self.msg_repo.get_by_id(self.log_msg_id)
        if refreshed is not None:
            await publish_message_updated(self.redis, self.proposal_id, refreshed)
        self._pending_count = 0
        self._last_flush_ts = monotonic()

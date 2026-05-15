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

import inspect
import logging
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Awaitable, Callable, Union
from urllib.parse import urlparse

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


CitationRef = dict[str, Any]
Span = dict[str, Any]
ActivityEvent = dict[str, Any]
EventCallback = Callable[[ActivityEvent], Union[Awaitable[None], None]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:  # noqa: BLE001
        return url


async def _invoke_event_cb(on_event: EventCallback, event: ActivityEvent) -> None:
    """Call on_event, awaiting if it returned a coroutine.

    Tolerates both sync callbacks (e.g. ``list.append``) and async ones.
    """
    result = on_event(event)
    if inspect.isawaitable(result):
        await result


async def process_stream(
    stream, *, on_event: EventCallback
) -> tuple[str, list[CitationRef], list[Span]]:
    """Consume an Anthropic ``messages.stream`` iterator.

    Calls ``on_event(activity_event_dict)`` for each search query Claude
    issues, each result URL it reads, and a final ``note`` event before
    return. Returns ``(body, citations, spans)``:

    - body: the concatenated assistant text (the markdown findings body)
    - citations: deduped-by-URL list of CitationRef dicts
    - spans: list of Span dicts referencing citations by their ``id``
    """
    body_parts: list[str] = []
    citations: list[CitationRef] = []
    spans: list[Span] = []

    async for event in stream:
        event_type = getattr(event, "type", None)

        if event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            if block is None:
                continue
            block_type = getattr(block, "type", None)
            if block_type == "tool_use" and getattr(block, "name", None) == "web_search":
                query = (getattr(block, "input", {}) or {}).get("query", "")
                if query:
                    await _invoke_event_cb(
                        on_event,
                        {"type": "search", "query": query, "ts": _now_iso()},
                    )
            elif block_type == "web_search_tool_result":
                for result in (getattr(block, "content", None) or []):
                    url = getattr(result, "url", "")
                    title = getattr(result, "title", "") or _parse_domain(url)
                    if url:
                        await _invoke_event_cb(
                            on_event,
                            {"type": "read", "url": url, "title": title, "ts": _now_iso()},
                        )

        elif event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta is not None and getattr(delta, "type", None) == "text_delta":
                body_parts.append(getattr(delta, "text", "") or "")

        elif event_type == "content_block_stop":
            block = getattr(event, "content_block", None)
            if block is None:
                continue
            block_type = getattr(block, "type", None)
            if block_type == "tool_use" and getattr(block, "name", None) == "web_search":
                # If the query wasn't captured at start (e.g. it arrives via
                # input_json_delta before the input is finalized), the final
                # block state would let us recover it here. The start path
                # above captures the common case; this is reserved for SDK
                # variations and intentionally a no-op today.
                pass
            elif block_type == "text":
                for c in (getattr(block, "citations", None) or []):
                    cit = _ensure_citation(citations, c)
                    spans.append({
                        "start": getattr(c, "start_block_index", 0),
                        "end": getattr(c, "end_block_index", 0),
                        "citation_ids": [cit["id"]],
                    })

    # A trailing note — gives the user a "synthesizing..." beat in the UI
    # between the last tool result and the findings card arriving.
    await _invoke_event_cb(
        on_event, {"type": "note", "text": "Synthesizing findings...", "ts": _now_iso()}
    )

    return "".join(body_parts), citations, spans


def _ensure_citation(citations: list[CitationRef], anth_cit) -> CitationRef:
    """De-dup citations by URL. Returns the (existing or new) CitationRef."""
    url = getattr(anth_cit, "url", "")
    for existing in citations:
        if existing["url"] == url:
            return existing
    new: CitationRef = {
        "id": len(citations) + 1,
        "url": url,
        "title": getattr(anth_cit, "title", "") or url,
        "domain": _parse_domain(url),
        "cited_text": getattr(anth_cit, "cited_text", "") or "",
    }
    citations.append(new)
    return new

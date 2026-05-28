"""Streaming-event handling for the run_research / run_benchmarks phases.

Two responsibilities split into well-named units:

- :class:`ActivityFlusher` — batched-flush primitive for a single
  ``*_activity_log`` chat message. Accumulates ``ActivityEvent`` rows,
  persists them in batches, commits, and publishes ``message_updated`` WS
  events.

- :func:`process_stream` — pure(ish) async function that consumes an
  Anthropic SDK message-stream and converts it into ``ActivityEvent`` calls
  to a provided callback while accumulating the final body, citation list,
  and span list.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Awaitable, Callable
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
EventCallback = Callable[[ActivityEvent], Awaitable[None]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:  # noqa: BLE001
        return url


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

    Span offsets are computed from the accumulated body text by matching
    each citation's ``cited_text`` as a verbatim substring. The Anthropic
    SDK's ``CitationsWebSearchResultLocation`` carries only ``url``,
    ``title``, ``cited_text`` and ``encrypted_index`` — there are no
    character-offset fields to read directly. Every citation is recorded;
    citations whose ``cited_text`` isn't a verbatim substring of the
    surrounding text block are kept without a body-anchored span (rather than
    emitted as degenerate ``{start: 0, end: 0}`` spans). Hosted ``web_search``
    frequently paraphrases, so dropping such citations would silently lose
    source attribution.
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
                    await on_event(
                        {"type": "search", "query": query, "ts": _now_iso()}
                    )
            # NOTE: web_search_tool_result.content is populated by
            # content_block_stop time, not _start. Result URLs are emitted
            # from the _stop branch below.

        elif event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta is not None and getattr(delta, "type", None) == "text_delta":
                body_parts.append(getattr(delta, "text", "") or "")

        elif event_type == "content_block_stop":
            block = getattr(event, "content_block", None)
            if block is None:
                continue
            block_type = getattr(block, "type", None)
            if block_type == "web_search_tool_result":
                # Results are materialized by stop-time in the real SDK.
                for result in (getattr(block, "content", None) or []):
                    url = getattr(result, "url", "")
                    title = getattr(result, "title", "") or _parse_domain(url)
                    if url:
                        await on_event(
                            {"type": "read", "url": url, "title": title, "ts": _now_iso()}
                        )
            elif block_type == "text":
                block_text = getattr(block, "text", "") or ""
                # The accumulated body so far ends with this block's text.
                # Compute where this block starts within the full body so
                # span offsets are body-relative, not block-relative.
                text_offset = sum(len(p) for p in body_parts) - len(block_text)
                # Cursor for multi-citation blocks — each citation searches
                # after the previous match to avoid overlapping spans when
                # the same snippet appears twice.
                cursor = 0
                for c in (getattr(block, "citations", None) or []):
                    if not (getattr(c, "url", "") or ""):
                        # No URL → can't render as a source link; drop it.
                        continue
                    # Record the source unconditionally. The citation (source
                    # attribution) is the primary value; the body-anchored span
                    # is a best-effort nicety on top.
                    cit = _ensure_citation(citations, c)
                    cited = getattr(c, "cited_text", "") or ""
                    if not cited:
                        continue
                    idx = block_text.find(cited, cursor)
                    if idx < 0:
                        # cited_text isn't a verbatim substring — Claude may
                        # have paraphrased. Keep the citation; just don't emit
                        # a body-anchored span. Future v2: fuzzy match.
                        continue
                    start = text_offset + idx
                    end = start + len(cited)
                    cursor = idx + len(cited)
                    spans.append(
                        {"start": start, "end": end, "citation_ids": [cit["id"]]}
                    )

    # A trailing note — gives the user a "synthesizing..." beat in the UI
    # between the last tool result and the findings card arriving.
    await on_event({"type": "note", "text": "Synthesizing findings...", "ts": _now_iso()})

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

# Design: Research transparency — plan, live activity, annotated findings

**Date:** 2026-05-15
**Status:** Approved (design) — pending spec review
**Area:** `backend/` + `frontend/` — transparency for the web-search-driven `run_research` and `run_benchmarks` pipeline phases

## Context

When the agency owner approves the template gate, NUPROP enqueues
`run_research` and `run_benchmarks` (chained in that order). Each phase calls
Claude with the native `web_search_20250305` tool, lets it run for 30–90s, and
finally writes a single combined `research_findings` chat message containing
both bodies as plain markdown.

Today the user experience during those 60–180 seconds is:

- The chat shows a generic progress event: **"Researching Pepsi Global…"**.
  It doesn't change. It doesn't say which queries Claude is running, which
  pages it's reading, or whether anything is actually happening.
- The agent uses one bulk `messages.create()` call (recently renamed to
  `messages_create` on the facade in `app/infrastructure/external/
  anthropic_client.py`). Streaming events from the SDK are discarded; only
  the final response is consumed. The web-search tool's `citations`
  metadata (which Anthropic returns per text block) is similarly thrown
  away — the worker concatenates `.text` and stores the result as plain
  markdown.
- Once research finishes, the user gets one big block of prose with no
  inline source attribution. To verify any specific claim, they'd have to
  re-run the searches themselves.

Two related pain points fall out of this:

1. **Felt latency** is much worse than actual latency. 60s of static
   "Researching…" feels broken even when the worker is healthily streaming
   tool events from Bedrock; we just aren't surfacing them.
2. **Defensibility** of the final research is weak. The agency owner can't
   point at a sentence in the findings card and say "this claim came from
   [reuters.com](#)" without re-doing the search themselves.

The Bedrock SDK already streams structured events for each tool call and
returns citation spans on each text block — both today, no model change
required. The transparency work is plumbing what's already in the response
through to the UI.

## Goals

1. **Pre-flight plan.** Before the slow research call starts, the user sees
   a short Haiku-generated card listing the specific search queries Claude
   plans to issue and one paragraph of rationale. Persisted as a chat
   message so it's auditable later.
2. **Live activity stream.** While the research call is running, every
   `web_search` tool call (the query) and every `web_search_tool_result`
   block (the URL/title Claude read) is surfaced as a row in a
   single live-updating "activity log" chat message. The user sees the
   timeline grow in real time. Persisted so a week-later open of the
   proposal still shows what Claude did.
3. **Annotated findings.** The final research / benchmarks output renders
   with inline hover-citation superscripts. Hovering a superscript shows
   the source title, domain, and the exact cited snippet. A sources list
   at the bottom of the card lists every citation in order. The chat
   message stores the citation graph in its `extra_data`; the `proposal`
   table stays plain markdown for downstream-agent compatibility.

Together these turn the research phase from a black box into something the
agency owner can defend claim-by-claim to a client.

## Non-goals (v2, not in this build)

- **No streaming for brief intake** — defer to the streaming-for-brief
  spec we sketched earlier. This build ships the `message_updated` WS event
  primitive that streaming brief intake will reuse, but does not retrofit
  the brief intake itself.
- **No structured citations for downstream agents.** `NarrativeGenerator`,
  `OutputGenerator`, `CostModelBuilder` continue to read `proposal.research`
  / `proposal.benchmarks` as plain markdown. They lose nothing relative to
  today and gain no awareness of citations. Future work can teach the
  narrative agent to preserve footnotes; out of scope here.
- **No cell-level annotations on benchmark tables.** Benchmarks output
  often contains markdown tables of pricing data. Hover citations apply at
  the markdown-body level (the prose between/around the tables); cell-level
  citation is deferred.
- **No DOCX/PDF citation rendering.** The annotated view lives in the chat
  card only. Exports to DOCX / proposal-site / PDF stay as today (plain
  prose, no footnotes). Adding footnotes to the document outputs is a
  follow-up.
- **No grouping of consecutive identical searches.** If Claude searches
  the same query twice (it sometimes does mid-loop), the activity log
  shows both. Audit fidelity over UI tidiness.
- **No tier-toggle UI for the user.** The Opus-for-research /
  Sonnet-for-benchmarks split is hardcoded. Future tier-toggle work belongs
  with the ideation tier-toggle (see ideation spec).
- **No real-time citations in the activity log.** Citations appear only on
  the final findings card. The activity log shows searches and reads, not
  per-claim attribution.
- **No re-running of just the plan (retry only re-runs the full phase).**
  If the user wants a different plan, they'd retry the whole phase via the
  existing `/chat/{id}/retry` endpoint.

## Architecture

Each web-search-driven phase emits exactly **three chat messages** plus a
stream of WebSocket events. The worker stays inside the existing ARQ + Redis
pub/sub + commit-before-broadcast pattern.

```
Worker enters run_research(proposal_id)
  │
  ├─ Step 1: PLAN (Haiku, ~1s)
  │    ├─ ai.complete_json(prompt=brief, tier=FAST, system=PLAN_SYSTEM)
  │    │     → { "queries": [...], "rationale": "..." }
  │    ├─ Persist message_type="research_plan"
  │    ├─ commit
  │    └─ publish new_message → drawer renders ResearchPlanCard
  │
  ├─ Step 2: ACTIVITY LOG INIT
  │    ├─ Persist message_type="research_activity_log"
  │    │     content="", extra_data={
  │    │       "phase": "research",
  │    │       "status": "running",
  │    │       "events": [],
  │    │     }
  │    ├─ commit
  │    └─ publish new_message → drawer renders ResearchActivityLog (empty + spinner)
  │
  ├─ Step 3: STREAMING RESEARCH (Opus 4.7, ~60s)
  │    ├─ async with ai.client.messages.stream(
  │    │       model=ANTHROPIC_OPUS_MODEL,
  │    │       max_tokens=4096,
  │    │       system=RESEARCH_SYSTEM,
  │    │       tools=[{"type": "web_search_20250305", ...}],
  │    │       messages=[{"role": "user", "content": user_msg}],
  │    │     ) as stream:
  │    │       for event in stream:
  │    │         on content_block_start:
  │    │           type=tool_use(name=web_search)         → append {type:"search", query}
  │    │           type=web_search_tool_result            → append {type:"read", url, title}
  │    │         on content_block_delta(text_delta)       → accumulate body
  │    │         on content_block_stop where block has .citations
  │    │                                                  → record spans + dedupe sources
  │    │
  │    │         every 5 events OR every 750ms:
  │    │           ├─ UPDATE activity_log.extra_data.events
  │    │           ├─ commit
  │    │           └─ publish message_updated  (NEW event type)
  │    │
  │    └─ on stream end:
  │         ├─ final flush of activity_log
  │         └─ activity_log.extra_data.status = "complete"
  │
  ├─ Step 4: FINDINGS
  │    ├─ Persist message_type="research_findings"
  │    │     content=accumulated_body (plain markdown)
  │    │     extra_data={
  │    │       "phase": "research",
  │    │       "citations": [ {id, url, title, domain, cited_text}, ... ],
  │    │       "spans":     [ {start, end, citation_ids: [...]}, ... ],
  │    │     }
  │    ├─ UPDATE proposal.research = accumulated_body  (plain text, unchanged contract)
  │    ├─ commit
  │    └─ publish new_message → drawer renders ResearchFindingsCard
  │
  └─ done — pipeline_state.current_phase advances per existing pipeline logic

(same shape for run_benchmarks, with Sonnet 4.6 instead of Opus and
 BENCHMARKS_PLAN_SYSTEM / BENCHMARKS_SYSTEM prompts)
```

The existing `_run_phase` shim in `app/workers/pipeline.py` continues to handle
the outer success/failure envelope (`job_status` bookkeeping, `pipeline_error`
broadcast on terminal failure). The streaming logic and the new message
shapes live inside `PipelineService.run_research` / `run_benchmarks`.

### Backward compatibility — what stays the same

- `proposal.research` and `proposal.benchmarks` remain `Text | None` columns
  containing plain markdown. Downstream agents (`NarrativeGenerator`,
  `OutputGenerator`, `CostModelBuilder`) read these unchanged.
- `run_research` and `run_benchmarks` continue to advance `pipeline_state`
  in the same way (research completion advances to `cost_model_review`,
  same as today).
- The existing `progress` WebSocket events (`{type: "progress", agent,
  status, detail}`) are no longer emitted by these two phases — they're
  superseded by the activity log + plan messages. Other phases
  (`build_cost_model`, `generate_narrative`, `generate_outputs`) keep
  using `progress` events as today.
- Worker shim and ARQ task registration are unchanged. No new worker
  function.

### Failure isolation

If the streaming research call fails partway through:

- The pre-flight plan message was already persisted — it stays. Audit
  trail intact.
- The activity log message is updated one final time:
  `extra_data.status = "failed"`, `extra_data.error = str(exc)`. The
  partial events captured before failure remain in `extra_data.events`.
- No `research_findings` message is created.
- `proposal.research` is **not** modified (so partial / corrupt output
  doesn't pollute the downstream agents).
- The existing `_run_phase` shim catches the exception, writes
  `pipeline_state.job_status = "failed"`, and publishes the existing
  `pipeline_error` WS event. The `/chat/{id}/retry` endpoint accepts the
  retry (per the existing `state == "failed"` check).
- On retry, a fresh plan + activity log + findings triplet is created. The
  old triplet is **not** deleted — the chat thread shows both attempts as
  separate timeline entries.

## Data model

**No schema changes.** Two existing tables stay as-is:

- `chat_messages.message_type: VARCHAR(30)` — accepts arbitrary string
  values today; the four new types are just additional values.
- `chat_messages.extra_data: JSONB` — already a free-form column.
- `proposals.research: Text | None`, `proposals.benchmarks: Text | None` —
  unchanged, plain markdown bodies.

### New chat-message types

| Type | Role | `extra_data` shape |
|---|---|---|
| `research_plan` | assistant | `{ "phase": "research", "queries": [str], "rationale": str }` |
| `research_activity_log` | assistant | `{ "phase": "research", "status": "running" \| "complete" \| "failed", "events": [ActivityEvent], "error"?: str }` |
| `research_findings` | assistant | `{ "phase": "research", "citations": [CitationRef], "spans": [Span] }` *(existing type, new fields)* |
| `benchmarks_plan` | assistant | same as `research_plan` with `"phase": "benchmarks"` |
| `benchmarks_activity_log` | assistant | same as `research_activity_log` with `"phase": "benchmarks"` |
| `benchmarks_findings` | assistant | same as `research_findings` with `"phase": "benchmarks"` *(new type — replaces today's "benchmarks section in the combined research_findings message")* |

The existing combined-section `research_findings` message in current
behavior contained both research AND benchmarks markdown as one body. After
this change, they split: `research_findings` carries only the research
body; `benchmarks_findings` is a new message with only benchmarks. Each is
annotated independently.

### `ActivityEvent` shape

```python
# Each event is a tagged dict, one of:

# 1. Claude issued a web_search tool call.
{ "type": "search",
  "query": "Pepsi Global rebrand 2024",
  "ts": "2026-05-15T14:32:11.123Z" }

# 2. Web search returned a result (one event per result URL — if Claude's
#    web_search call returned 5 URLs, that's 5 events).
{ "type": "read",
  "url": "https://reuters.com/business/pepsi-q4-2024",
  "title": "Pepsi Q4 2024 earnings",
  "ts": "2026-05-15T14:32:14.987Z" }

# 3. Worker-emitted free-form note (e.g. when stream completes the
#    tool-use loop and begins synthesizing the final text).
{ "type": "note",
  "text": "Synthesizing findings...",
  "ts": "2026-05-15T14:32:28.011Z" }
```

`ts` is ISO-8601 UTC, captured at the moment the worker observed the event.

### Findings `extra_data` — `CitationRef` and `Span`

```python
CitationRef = {
    "id": int,            # 1-indexed, sequential within this findings message
    "url": str,
    "title": str,         # Anthropic returns this; fall back to URL if empty
    "domain": str,        # parsed from URL for the popover badge — e.g. "reuters.com"
    "cited_text": str,    # exact snippet Claude cited (Anthropic returns this)
}

Span = {
    "start": int,                  # character offset within `content` (the plain markdown body)
    "end": int,                    # character offset within `content`
    "citation_ids": list[int],     # one or more CitationRef.ids this span supports
}
```

Citations are de-duplicated by URL within a single findings message — if
Claude cites the same Reuters article in three different sentences, the
sources list has one entry, and three spans each reference that one
citation id. Pseudo-code:

```python
def _ensure_citation(citations: list[CitationRef], anth_cit) -> CitationRef:
    for existing in citations:
        if existing["url"] == anth_cit.url:
            return existing
    new = {
        "id": len(citations) + 1,
        "url": anth_cit.url,
        "title": anth_cit.title or anth_cit.url,
        "domain": _parse_domain(anth_cit.url),
        "cited_text": anth_cit.cited_text,
    }
    citations.append(new)
    return new
```

`Span.start` and `Span.end` are offsets within the **plain markdown body**
(the `content` field of the message), not within the rendered HTML. The
frontend converts these to render-time DOM positions via a single
post-render walk.

## WebSocket protocol

One new event type:

```typescript
// NEW event: full updated message, sent on activity-log flushes.
{
  type: "message_updated",
  message: ChatMessageResponse,    // the full message after the update
}
```

Existing event types stay as today:
- `new_message` — for the plan, the activity_log on creation, and the
  findings.
- `typing` — unchanged.
- `phase_change` — unchanged.
- `progress` — still used by other phases (`build_cost_model`,
  `generate_narrative`, `generate_outputs`).
- `pipeline_error` — unchanged.

The frontend store gets one new handler — `updateMessage(msg)` that finds
the message by id within the appropriate channel slice and replaces it. WS
routing is by event type:

```typescript
ws.onmessage = (e) => {
  const evt = JSON.parse(e.data)
  switch (evt.type) {
    case 'new_message':      store.addMessage(evt.message); break
    case 'message_updated':  store.updateMessage(evt.message); break
    case 'typing':           store.setTyping(evt.typing); break
    case 'phase_change':     store.setPhase(evt.phase); break
    case 'progress':         store.pushProgress(evt); break
    case 'pipeline_error':   store.setPipelineError(evt); break
  }
}
```

## Worker implementation

### Tier choice

| Phase | Tier | Bedrock model id |
|---|---|---|
| Pre-flight plan (research) | FAST | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Research streaming call | HEAVY | `global.anthropic.claude-opus-4-7` |
| Pre-flight plan (benchmarks) | FAST | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Benchmarks streaming call | BALANCED | `global.anthropic.claude-sonnet-4-6` |

**Why asymmetric:** research is the higher-stakes phase. Opus's better
search-strategy reasoning, better synthesis across conflicting sources,
and stronger uncertainty marking ("I couldn't find a definitive source on
this") directly serve the "defendable" goal. Benchmarks is more structured
(find a number, find another number, tabulate) — Sonnet handles it well at
1/3 the cost. The pre-flight plans are short JSON outputs that Haiku nails.

**Opus 4.7 constraints to honour:** the SDK call must **not** pass
`temperature`, `top_p`, or `top_k` (Opus 4.7 400s on those). `ResearchAgent`
today already passes none of them in the `messages.create(...)` call —
verified during this design. The streaming call replaces that bulk call
with `messages.stream(...)` but keeps the same parameter set. If a future
caller adds `temperature`, the existing `AIService._build_kwargs` already
strips it for HEAVY-tier calls; keep using that path.

### Activity-log batched flush

A bounded-writes strategy so we don't commit on every streamed event but
still feel live:

```python
_FLUSH_MAX_EVENTS = 5
_FLUSH_MAX_INTERVAL_S = 0.75

class _ActivityFlusher:
    def __init__(self, session, msg_repo, redis, log_msg_id, proposal_id):
        ...
        self._buffered: list[ActivityEvent] = []
        self._all_events: list[ActivityEvent] = []
        self._last_flush_ts = monotonic()

    async def append(self, event: ActivityEvent) -> None:
        self._buffered.append(event)
        self._all_events.append(event)
        if (
            len(self._buffered) >= _FLUSH_MAX_EVENTS
            or (monotonic() - self._last_flush_ts) >= _FLUSH_MAX_INTERVAL_S
        ):
            await self.flush()

    async def flush(self, *, final_status: str | None = None, error: str | None = None) -> None:
        if not self._buffered and final_status is None:
            return
        extra = {
            "phase": self.phase,
            "status": final_status or "running",
            "events": list(self._all_events),
        }
        if error:
            extra["error"] = error
        await self.msg_repo.update(self.log_msg_id, extra_data=extra)
        await self.session.commit()
        msg = await self.msg_repo.get_by_id(self.log_msg_id)
        await publish(self.redis, self.proposal_id, {
            "type": "message_updated",
            "message": ChatMessageResponse.model_validate(msg).model_dump(mode="json"),
        })
        self._buffered.clear()
        self._last_flush_ts = monotonic()
```

The flusher is constructed once at the start of streaming, called from the
event loop in `messages.stream`, and given a final `flush(final_status=...)`
when the stream ends (or fails). The "every 750ms" rule is enforced on
`.append()`, which is a small inaccuracy (events that arrive in a quiet
period don't get flushed until the next event comes in). Acceptable for v1.
A `asyncio.create_task` with a periodic flush is a cleaner alternative but
adds task-lifecycle complexity for marginal benefit.

### Streaming event handling

Pseudo-code for the body of `run_research` (replaces the bulk
`messages_create` call):

```python
async with ai.client.messages.stream(
    model=settings.ANTHROPIC_OPUS_MODEL,
    max_tokens=4096,
    system=RESEARCH_SYSTEM,
    tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}],
    messages=[{"role": "user", "content": user_msg}],
) as stream:
    flusher = _ActivityFlusher(...)
    citations: list[CitationRef] = []
    spans: list[Span] = []
    body_parts: list[str] = []
    body_offset = 0

    async for event in stream:
        if event.type == "content_block_start":
            block = event.content_block
            if block.type == "tool_use" and block.name == "web_search":
                await flusher.append({
                    "type": "search",
                    "query": block.input.get("query", ""),
                    "ts": _now_iso(),
                })
            elif block.type == "web_search_tool_result":
                for result in (block.content or []):
                    await flusher.append({
                        "type": "read",
                        "url": result.url,
                        "title": result.title or _parse_domain(result.url),
                        "ts": _now_iso(),
                    })

        elif event.type == "content_block_delta":
            if event.delta.type == "text_delta":
                body_parts.append(event.delta.text)
                body_offset += len(event.delta.text)

        elif event.type == "content_block_stop":
            block = event.content_block
            if block.type == "text" and getattr(block, "citations", None):
                for c in block.citations:
                    cit = _ensure_citation(citations, c)
                    spans.append({
                        "start": c.start_block_index,
                        "end": c.end_block_index,
                        "citation_ids": [cit["id"]],
                    })

    await flusher.append({"type": "note", "text": "Synthesizing findings...", "ts": _now_iso()})
    await flusher.flush(final_status="complete")

body = "".join(body_parts)
findings_msg = await msg_repo.create(
    proposal_id=proposal_id,
    role=MessageRole.ASSISTANT.value,
    message_type="research_findings",
    content=body,
    extra_data={"phase": "research", "citations": citations, "spans": spans},
    phase="research",
)
await proposal_repo.update(proposal_id, research=body)
await session.commit()
await emit_new_message(redis, proposal_id, findings_msg)
```

**`block.citations` shape from Anthropic SDK** — per the SDK docs, each
text block's `.citations` array contains objects with `url`, `title`,
`cited_text`, and `start_block_index` / `end_block_index` (the offsets into
the assistant's output where this citation applies). The `_ensure_citation`
helper dedups by URL. Spans use the SDK's offsets directly — they're
already the right reference frame (within the assistant's `text` content).

**Failure-path code path:**

```python
try:
    # ...all of the above streaming code...
except Exception as exc:  # noqa: BLE001
    logger.exception("run_research streaming failed for %s", proposal_id)
    await flusher.flush(final_status="failed", error=str(exc))
    raise  # let the existing _run_phase wrapper handle pipeline_state + WS pipeline_error
```

The flusher's final flush ensures the activity log card reflects the
failed state in the UI; re-raising lets the existing wrapper do its
`job_status="failed"` bookkeeping unchanged.

### Pre-flight plan generation

Both research and benchmarks share the same shape but different prompts.
The plan is one Haiku call returning structured JSON:

```python
_RESEARCH_PLAN_SYSTEM = """\
You are NUPROP's research planner. You're about to do thorough web research
on a client to back a high-value design / branding / professional-services
proposal. Before research begins, the user wants a short summary of what
you intend to look at and why.

Given the brief (as JSON), return:
  - "queries":   3-6 specific web-search queries you'd run (each a string,
                 phrased like a real search query — concrete, not vague)
  - "rationale": one short paragraph (2-3 sentences) explaining what these
                 queries together will tell us, and why those things matter
                 for shaping the proposal.

Return ONLY valid JSON. No prose, no markdown fences."""

_BENCHMARKS_PLAN_SYSTEM = """\
You are NUPROP's pricing-benchmark planner. You're about to find market
pricing for the deliverables in this brief. Before benchmarking begins,
the user wants a short summary of what you'll look at.

Given the brief and a list of deliverable categories, return:
  - "queries":   3-6 specific search queries you'd run for pricing data
                 (each a string — e.g. "logo design agency rates India
                 2024" not "design pricing")
  - "rationale": one short paragraph explaining what these queries
                 collectively will tell us about market rates and how
                 we'll use it.

Return ONLY valid JSON. No prose, no markdown fences."""
```

Worker code:

```python
plan = await ai.complete_json(
    prompt=json.dumps({"brief": proposal.brief}),
    tier=Tier.FAST,
    system=_RESEARCH_PLAN_SYSTEM,
    max_tokens=512,
)
# plan is { "queries": [...], "rationale": "..." }
plan_msg = await msg_repo.create(
    proposal_id=proposal_id,
    role=MessageRole.ASSISTANT.value,
    message_type="research_plan",
    content="",  # rendering reads from extra_data; content stays empty for this type
    extra_data={"phase": "research", **plan},
    phase="research",
)
await session.commit()
await emit_new_message(redis, proposal_id, plan_msg)
```

`content` is empty for plan messages — the frontend renders entirely from
`extra_data.queries` + `extra_data.rationale`. Putting it in `extra_data`
(not `content`) keeps the data structured, lets the UI render a proper
list + paragraph instead of stringifying.

## Frontend

### New components

| File | Component |
|---|---|
| `frontend/src/components/chat/research-plan-card.tsx` | `<ResearchPlanCard />` — renders both `research_plan` and `benchmarks_plan` types |
| `frontend/src/components/chat/research-activity-log.tsx` | `<ResearchActivityLog />` — renders both `research_activity_log` and `benchmarks_activity_log` types |
| `frontend/src/components/chat/research-findings-card.tsx` | `<ResearchFindingsCard />` — replaces the existing `<ResearchCard />`; renders `research_findings` and `benchmarks_findings` |
| `frontend/src/components/chat/citation-popover.tsx` | `<CitationPopover />` — sub-component inside `<ResearchFindingsCard />` |

The existing `<ResearchCard />` (defined inside `message-bubble.tsx`) is
**deleted**. The new `<ResearchFindingsCard />` is its successor. Existing
test fixtures don't reference the type at the rendering layer, so this is
safe.

### `message-bubble.tsx` routing

The dispatch in `message-bubble.tsx` adds five new branches before the
default text-bubble fallback:

```tsx
if (message.message_type === 'research_plan' || message.message_type === 'benchmarks_plan')
  return <ResearchPlanCard message={message} />

if (message.message_type === 'research_activity_log' || message.message_type === 'benchmarks_activity_log')
  return <ResearchActivityLog message={message} />

if (message.message_type === 'research_findings' || message.message_type === 'benchmarks_findings')
  return <ResearchFindingsCard message={message} />
```

### `<ResearchPlanCard />` — render shape

- Card: light blue-gray background, rounded corners, slight border.
- Header: `🔍 Research plan` or `📈 Benchmarks plan` (chosen by
  `extra_data.phase`).
- Bulleted list of `extra_data.queries`.
- One paragraph of `extra_data.rationale` below.
- No interactions.

### `<ResearchActivityLog />` — render shape

- Card: same light blue-gray palette.
- Header: `⚡ Research activity` (or `⚡ Benchmark activity`) on the left;
  status badge on the right.
  - `running` → small spinner + "running"
  - `complete` → green check + "complete · {duration}s · {N} searches · {M} sources"
  - `failed` → amber warning + the error message in a tooltip on hover
- Body: an ordered list of events from `extra_data.events`:
  - `search` events: 🔍 icon, query in monospace.
  - `read` events: 📄 icon, domain in bold, title truncated to ~50 chars
    on overflow.
  - `note` events: 🧠 icon, the note text.
  - Each event also shows the timestamp in `HH:MM:SS` format on the left.
- Auto-scrolls to the bottom as new events arrive (while `status =
  "running"`).
- **Collapse behaviour:**
  - While `status = "running"`: always expanded.
  - When `status` becomes `complete`: collapses to a one-liner summary
    with a chevron. Default state for completed phases is collapsed.
  - On `failed`: stays expanded so the user sees what got partway done.
- Accessibility: the `<ol>` has `aria-live="polite"`. Status icon has an
  `aria-label`.

### `<ResearchFindingsCard />` — render shape

- Card: light blue-gray for research, light amber for benchmarks
  (differentiated palette so the user can tell sections apart at a
  glance during a scrollback).
- Header: `📑 Research findings` or `📊 Pricing benchmarks`.
- Body: the markdown in `message.content` rendered with the existing
  markdown component (the same one used elsewhere in NUPROP).
- After the markdown renders, a one-pass DOM walk injects citation
  superscripts at the offsets recorded in `extra_data.spans`. Each
  superscript is a `<button>` with `aria-describedby` pointing at the
  popover, so keyboard users can tab to it and Enter/Space opens.
- Hover or focus on a superscript triggers `<CitationPopover />`
  (positioned via Floating UI or a similar library; ~400px wide; closes
  on mouseleave / Esc / focus loss).
- Below the markdown: a horizontal rule, then a **Sources** section
  listing all citations in id-order. Each entry is `[N] {title} · {domain}`,
  clickable (opens the URL in a new tab with `rel="noopener noreferrer"`).
- Hovering a sources-list entry highlights the matching superscripts in
  the body (two-way visual link). Implemented by giving the entry and
  the spans a shared `data-citation-id` attribute and toggling a CSS
  class on hover.

### `<CitationPopover />` — render shape

Anchored to the superscript it was triggered from. Layout:

```
┌──────────────────────────────────────────────────┐
│  reuters.com                          [×]        │
│  Pepsi Q4 2024 earnings                          │
│                                                  │
│  "Revenue grew 8.2% YoY to $91.4B, driven by    │
│   international FMCG markets..."                 │
│                                                  │
│  Open source ↗                                   │
└──────────────────────────────────────────────────┘
```

- Domain badge at top-left as a small chip.
- Title in bold (truncated to ~80 chars).
- Cited snippet (`extra_data.citations[i].cited_text`) as a block quote
  with a subtle left border. Limited to ~4 lines of text; the rest
  truncates with an ellipsis (full content available by opening the
  source).
- "Open source ↗" — link to the citation URL.

### Citation-superscript injection

The post-render DOM walk works like this:

1. After the markdown component renders, its container has a known DOM
   subtree of rendered HTML.
2. A `useEffect` walks the subtree, accumulating character offsets across
   text nodes.
3. For each `span` in `extra_data.spans`, find the text node containing
   `span.end` and inject a `<sup>` element right after that character.
4. The `<sup>` carries `data-citation-id` attributes for all the citation
   ids it represents (a single span can reference multiple citations).
5. Re-renders of the same findings message (which only happen on
   `message_updated` if the worker corrects something — rare) re-run the
   walk; idempotent because we remove prior injected `<sup>` elements
   first.

For a body of ~5k chars and ~20 spans, this completes in <1ms in
benchmarks. No perf concern.

### Store updates

`chat-store.ts` gets one new action — `updateMessage(msg: ChatMessage)`:

```typescript
updateMessage: (msg: ChatMessage) =>
  set((state) => {
    const slice = msg.channel === 'ideation' ? 'ideationMessages' : 'messages'
    const list = state[slice] as ChatMessage[]
    const idx = list.findIndex((m) => m.id === msg.id)
    if (idx < 0) return {}
    const next = [...list]
    next[idx] = msg
    return { [slice]: next } as Partial<ChatState>
  }),
```

The action is a no-op when the message id isn't in the list — a defensive
guard against races (the WS connection sometimes delivers updates after a
proposal switch).

### WS routing

The WebSocket handler routes by event type. Existing handlers stay; one
new branch for `message_updated`:

```typescript
ws.onmessage = (e) => {
  const evt = JSON.parse(e.data)
  switch (evt.type) {
    case 'new_message':       store.addMessage(evt.message); break
    case 'message_updated':   store.updateMessage(evt.message); break  // NEW
    case 'typing':            store.setTyping(evt.typing); break
    case 'phase_change':      store.setPhase(evt.phase); break
    case 'progress':          store.pushProgress(evt); break
    case 'pipeline_error':    store.setPipelineError(evt); break
  }
}
```

## Test strategy

### Backend

- **Plan generation:** stub `AIService.complete_json` to return a fixed
  plan; assert one `research_plan` message lands on the proposal with
  `extra_data.queries` and `extra_data.rationale` matching the stub.
- **Streaming dispatch:** stub `AIService.client.messages.stream` with a
  synthetic event sequence (a few `content_block_start` tool_use events, a
  `web_search_tool_result`, some `text_delta`s, and a final text block
  with `citations`). Assert:
  - The activity log message is created with an empty `events` array.
  - One or more `message_updated` WS events fire during the run.
  - The final activity log has `status="complete"` and the full event
    sequence.
  - A `research_findings` message lands with the expected `content` body,
    `citations`, and `spans`.
  - `proposal.research` is set to the body.
- **De-dup of citations:** synthetic stream emits two citations for the
  same URL with different `start_block_index`; assert `extra_data.citations`
  has one entry and `extra_data.spans` has two entries both pointing at
  the same citation id.
- **Failure path:** synthetic stream raises mid-way; assert:
  - The activity log message is updated with `status="failed"` and the
    error text in `extra_data.error`.
  - No `research_findings` message is created.
  - `proposal.research` is unchanged.
  - The exception propagates (so the existing `_run_phase` wrapper
    handles `job_status="failed"` as usual).
- **Batched-flush bound:** with a synthetic stream of 50 events,
  assert `<= 15` `message_updated` events fire (50 / 5 = 10 plus tolerance
  for the time-based flush).
- **Tier selection:** assert the streaming call uses
  `ANTHROPIC_OPUS_MODEL` for research and `ANTHROPIC_DEFAULT_MODEL` for
  benchmarks (capture the kwargs passed to `messages.stream`).
- **Plan tier:** assert the plan call uses `Tier.FAST`.
- **Benchmarks symmetry:** the test suite duplicates the research tests
  for the benchmarks phase to verify the same shape on `benchmarks_plan`,
  `benchmarks_activity_log`, and `benchmarks_findings` messages.
- **Existing test fixtures:** `test_pipeline_service.py` tests for
  `run_research` and `run_benchmarks` need to update their assertions —
  today they mock `ResearchAgent.research_client` / `BenchmarkAgent.
  find_benchmarks` and assert `proposal.research` is set. The new
  implementation no longer calls those agent methods at all. Migrate the
  mocks to `AIService.client.messages.stream`.

### Frontend

- **`<ResearchPlanCard />`:** renders the bulleted queries from
  `extra_data.queries`, the rationale paragraph from `extra_data.rationale`.
  Both `research_plan` and `benchmarks_plan` go through the same component
  with the phase-aware header.
- **`<ResearchActivityLog />`:**
  - Renders search / read / note events with the correct icons.
  - On `status="running"`: shows the spinner; auto-scrolls to bottom.
  - On `status="complete"`: collapses to one-liner summary; chevron
    expands.
  - On `status="failed"`: stays expanded; shows the error in the
    badge tooltip.
- **`<ResearchFindingsCard />`:**
  - Renders the markdown body.
  - Injects citation superscripts at the right offsets (assert with a
    fixture body + spans; query the DOM for `<sup data-citation-id>`).
  - Hovering a superscript triggers the popover (RTL `userEvent.hover`).
  - The sources list at the bottom lists every citation in id-order;
    each is a link to its URL with `target=_blank rel=noopener noreferrer`.
- **`<CitationPopover />`:** renders title, domain, cited snippet, and
  the open-source link.
- **Store `updateMessage`:** replaces an existing message by id; no-op if
  the id isn't found.
- **WS routing:** `message_updated` event hits `updateMessage`, not
  `addMessage`.
- **End-to-end (existing chat tests):** confirm the new message types
  flow through `<MessageBubble />`'s dispatch and don't fall through to
  the default text bubble.

## Open questions

1. **Activity log default collapse on completion.** The spec proposes
   collapsing to a one-liner once `status = "complete"`. An alternative
   is to leave it expanded so the audit trail is always one scroll away.
   Implementation difference is one CSS state. Plan-stage decision; tune
   from real usage.

2. **Plan generation cost when the brief is empty.** If the user
   approves the template gate before completing the brief intake (which
   the current pipeline doesn't allow today, but might in v2), the plan
   call would receive an empty brief and produce generic queries. Not a
   bug given current pipeline ordering; flag if the ordering ever
   changes.

3. **`message_updated` payload size.** The full message including the
   growing events array is re-sent on every flush. For ~50 events the
   payload is a few KB. If we ever see this become a bandwidth problem
   we can switch to a delta-only event (`events_appended: [...]`) but
   the simpler full-replace is fine for v1.

## Self-review

- **Placeholder scan:** No "TBD", "TODO", "later", "appropriate", "edge
  cases". The two `..." or "...`-style ellipses in the architecture flow
  diagram are sequence ellipses, not unfilled slots. The "Open
  questions" section explicitly names deferred decisions.
- **Internal consistency:**
  - Tier choice (Opus research, Sonnet benchmarks, Haiku plan) appears
    consistently in Goals, Architecture, Worker implementation, and Test
    strategy.
  - The three-message-per-phase shape (`*_plan`, `*_activity_log`,
    `*_findings`) is used identically across architecture, data model,
    worker, and frontend sections.
  - `proposal.research` and `proposal.benchmarks` as plain markdown is
    consistent in Goals (item 3), Architecture (Backward compatibility),
    and Data model.
  - The `message_updated` WS event is defined once and used consistently
    in worker, WebSocket protocol, store, and routing sections.
  - De-dup-by-URL for citations is specified in Data model and exercised
    in Test strategy.
- **Scope check:** the v1 surface is one new WS event type, two
  worker-level changes (plan call + streaming refactor) in each of two
  phases, six new frontend components / branches, and one new store
  action. No schema changes. v2 deferrals are explicit.
- **Ambiguity check:**
  - Batched-flush rule is specific: "every 5 events OR every 750ms".
  - Citation de-dup key is specific: "by URL".
  - The `<sup>` injection mechanism is named: a post-render DOM walk.
  - Collapse behaviour on completion is specified (collapse to one-liner;
    expand on failure).
  - The one open ambiguity — whether to default-collapse the completed
    activity log — is listed in Open questions as a plan-stage decision.

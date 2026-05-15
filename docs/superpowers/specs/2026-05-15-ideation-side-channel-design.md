# Design: Ideation side-channel

**Date:** 2026-05-15
**Status:** Approved (design) — pending spec review
**Area:** `backend/` + `frontend/` — adds a read-only Claude side-channel attached to each proposal

## Context

NUPROP today has one chat surface per proposal — the main thread that drives
the structured brief-intake → template → research → cost-model → narrative →
outputs pipeline. Every message there feeds the formal pipeline; there is no
way to think out loud with the model without committing to that flow.

The agency owner often wants a different mode: *"what if we positioned this
as a retainer instead?", "what objections might Pepsi raise on the cost
model?", "if we cut the budget by 30%, what would we drop?"*. Today those
conversations have to happen outside NUPROP (a separate Claude.ai tab, with
the user re-explaining everything) or by polluting the main thread, which
re-triggers brief intake and confuses the pipeline state.

## Goals

- A **side-channel chat thread** per proposal, accessible at any point in the
  proposal's lifecycle — from the moment it's created (no brief yet) through
  to `complete` (outputs generated). No phase gating.
- The side-channel has **full read-only context** of whatever the main
  pipeline has produced so far (brief, research, benchmarks, cost model,
  narrative). Claude grounds its answers in that context.
- Conversations in the side-channel **never mutate** the proposal or the main
  pipeline. It's a thinking surface, not an editing surface.
- The side-channel reuses NUPROP's existing message / worker / WebSocket
  infrastructure rather than introducing a parallel stack.
- The UI signals clearly that ideation is a different context — visually
  distinct from the main chat, with a one-line caveat that it's read-only.

## Non-goals (v2, not in this build)

- **Multiple named threads per proposal** — MVP is one persistent ideation
  thread per proposal.
- **Apply suggestions back to the proposal** — no structured-edit mechanism;
  the user manually re-enters anything they want to keep in the main flow.
- **Streaming responses** — defer to the same future work that brings
  streaming to brief intake.
- **Server-side unread tracking** (`last_read_at` per channel per user).
- **Tier toggle (Sonnet / Opus / Haiku) in the drawer UI** — Sonnet 4.6 is
  hardcoded.
- **Cross-proposal ideation** ("how did similar past clients go?") —
  requires retrieval over agency history.
- **Phase-keyed system prompts** — the one generic prompt with full context
  handles all phases.
- **Drawer "context changed" indicator** — if the main pipeline finishes a
  phase mid-ideation, the user manually re-opens the drawer to reload.
- **Export ideation thread** (markdown / PDF).
- **Sharing / collaboration / presence indicators** — the data model already
  supports multi-user access (any agency user with proposal access reads the
  same thread), but presence and turn-taking are deferred.
- **Retry endpoint for ideation failures** — the user re-prompts.

## Architecture

```
                       Proposal
                          │
        ┌─────────────────┼─────────────────┐
        │                                   │
   ChatMessage                          ChatMessage
   channel="main"                       channel="ideation"  ← NEW
        │                                   │
        │                                   │
  Main pipeline                         IdeationService
  (existing)                              │
        │                                   │
  ARQ worker                            ARQ worker
  (analyze_brief, run_research,         (run_ideation)   ← NEW
   build_cost_model, ...)                  │
        │                                   │
   commits → publishes WS               commits → publishes WS
        │                                   │
        └─────────────►  Redis pub/sub  ◄───┘
                              │
                       ws_event_subscriber
                              │
                       ws_manager.broadcast(proposal_id, payload)
                              │
                              ▼
                       browser WS client
                              │
            ┌─────────────────┴─────────────────┐
            │ message.channel === "main"       │ message.channel === "ideation"
            │ → main chat state                │ → drawer chat state
```

Ideation messages **share the same infrastructure** as the main pipeline
(table, repository, worker, Redis pub/sub bridge, WebSocket endpoint). The
only fork is on a new `channel` column on `ChatMessage` and a corresponding
filter in the message-list repository.

The ideation worker phase (`run_ideation`) follows the same commit-before-
broadcast pattern as the rest of the pipeline. A user-facing send-message
request enqueues the worker job and returns immediately with just the user
message; the assistant reply arrives via the WebSocket once the worker has
committed it.

### Read-only invariant

The ideation worker reads the proposal and its main-channel messages but
**never writes to** `proposal.brief`, `proposal.research`, `proposal.cost_model`,
`proposal.covering_letter`, `proposal.narrative_*`, or `proposal.pipeline_state`.
It writes only:

- One row to `chat_messages` with `channel="ideation"`, role=user (the user's
  prompt — written by the API process, not the worker).
- One row to `chat_messages` with `channel="ideation"`, role=assistant (the
  Claude response — written by the worker, committed before broadcast).

That's the entire write surface. Enforced by `IdeationService` not having
access to any non-`chat_messages` write path.

### Failure isolation

An ideation worker failure must not affect the main pipeline:

- Ideation phase status is **not** written to `proposal.pipeline_state.job_status`
  — that field tracks the main pipeline only, and contaminating it would risk
  blocking gate approvals.
- On failure, the worker writes one `chat_messages` row with `channel="ideation"`,
  role=`system`, type=`error`, and the error text in `content`. The frontend
  renders it as an inline error block in the drawer thread.
- No retry endpoint. The user re-prompts; each prompt is a fresh job.

## Data model

One additive column on `ChatMessage`:

```python
# backend/app/infrastructure/db/models/chat_message.py
class ChatMessage(BaseModel):
    # ... existing fields ...
    channel: Mapped[str] = mapped_column(
        String(20),
        default="main",
        server_default="main",
        nullable=False,
    )
```

Index added to support the drawer's "fetch this proposal's ideation thread"
query without touching main-thread queries:

```sql
CREATE INDEX ix_chat_messages_proposal_channel_created
    ON chat_messages (proposal_id, channel, created_at);
```

An Alembic migration adds the column with the server_default so existing rows
get `"main"` automatically. The migration also creates the new index.

**Why a string, not an enum:** strings let us add channels (`"draft"`,
`"reviewer"`, named ideation threads) without a schema migration. The Python
layer can tighten to a `MessageChannel` enum if we want type safety; the DB
representation stays a `VARCHAR(20)`.

### Repository change

`ChatMessageRepository.list_by_proposal` gains a `channel` kwarg with a default
of `"main"` so every existing caller keeps current behavior:

```python
async def list_by_proposal(
    self,
    proposal_id: UUID | str,
    skip: int = 0,
    limit: int = 200,
    channel: str = "main",
) -> list[ChatMessage]:
    ...
```

`ChatMessageRepository.create` does **not** require a channel kwarg — callers
that don't pass one get `"main"` from the column default. New ideation paths
pass `channel="ideation"` explicitly.

### Migration safety

The column has a server_default, so the migration is a single online ALTER
TABLE. The new index can be created online (PostgreSQL `CREATE INDEX
CONCURRENTLY` in production; SQLite ignores the keyword). No backfill needed —
the column default takes care of existing rows.

## Worker phase: `run_ideation`

New phase added to `PipelineService` (or as a separate `IdeationService` if we
want hard isolation — see "Open questions" below).

```python
# backend/app/services/ideation_service.py  (new module)
class IdeationService:
    def __init__(self, session: AsyncSession, redis):
        self.session = session
        self.redis = redis
        self.proposal_repo = ProposalRepository(session)
        self.msg_repo = ChatMessageRepository(session)
        self.ai = get_ai_service()           # AsyncAnthropicBedrock under the hood

    async def run_ideation(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return

        # 1. Load conversation history for the ideation channel only.
        history = await self.msg_repo.list_by_proposal(
            proposal_id, channel="ideation", limit=200,
        )
        messages = [
            {"role": m.role, "content": m.content}
            for m in history
            if m.role in (MessageRole.USER.value, MessageRole.ASSISTANT.value)
        ]

        # 2. Build the proposal-context system prompt and call Sonnet 4.6
        #    with cache_control on the system block. Use AIService.messages_create
        #    (the escape hatch) so we can pass system as a list of blocks; the
        #    high-level AIService.complete signature only accepts str today.
        system_text = _build_ideation_system_prompt(proposal)
        response = await self.ai.messages_create(
            model=self.ai.model_for(Tier.BALANCED),          # Sonnet 4.6
            max_tokens=2048,
            temperature=0.7,
            system=[{
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        )
        response_text = response.content[0].text

        # 3. Persist the assistant message on the ideation channel.
        assistant_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.TEXT.value,
            content=response_text,
            phase="ideation",
            channel="ideation",
        )
        await self.session.commit()                          # commit BEFORE broadcast

        # 4. Publish WS event so the drawer renders the message.
        await self._emit_message(proposal_id, assistant_msg)

    async def _emit_message(self, proposal_id, msg) -> None:
        await publish(self.redis, str(proposal_id), {
            "type": "new_message",
            "message": ChatMessageResponse.model_validate(msg).model_dump(mode="json"),
        })
```

`AIService.messages_create` is the existing escape hatch on `app/services/llm.py`
designed for exactly this case (prompt caching, tool-use, vision) — caller
builds the kwargs, including a list-form `system` with `cache_control`, and
passes them through to `AsyncAnthropicBedrock` directly. `model_for(Tier.BALANCED)`
resolves the tier to its configured Bedrock model ID.

The phase is wired into the ARQ worker via the same `_run_phase` shim used by
the main pipeline (`backend/app/workers/pipeline.py`), so a phase exception
becomes a terminal-failed state and emits a `pipeline_error`-equivalent
event. The handler **does not** call `_set_job_status` — that touches
`proposal.pipeline_state`, which ideation must not mutate. Instead, on a
caught exception, the handler writes a single error message to
`chat_messages` with `channel="ideation"`, role=`system`, type=`error`.

The job_id uses the user message's UUID as the idempotency suffix (same
pattern as the brief-intake fix from earlier today), so each ideation send is
a fresh job.

## API surface

Two new routes under the existing `/chat/{proposal_id}` prefix:

```
GET  /chat/{proposal_id}/ideation/messages
     → list[ChatMessageResponse]  (filtered to channel="ideation")
     → 404 if the proposal doesn't belong to the requesting agency

POST /chat/{proposal_id}/ideation/send
     Body:   SendMessageRequest { content: string }
     Status: 201
     Body:   list[ChatMessageResponse]  — the user message only;
             the assistant reply arrives over the WebSocket
```

Both routes use the same `get_current_agency_id` dependency and ownership
check as the main `/chat/{id}/*` routes.

No `/ideation/retry` endpoint. If the assistant message fails, an error block
appears in the drawer thread and the user re-prompts.

### ViewModel additions

`ChatViewModel` gets two new methods that mirror its existing send/messages
helpers, with `channel="ideation"` plumbed through:

```python
async def get_ideation_messages(self, proposal_id, agency_id, ...) -> list[ChatMessage] | None:
    ...  # ownership check + msg_repo.list_by_proposal(channel="ideation")

async def send_ideation_message(self, proposal_id, agency_id, content) -> list[ChatMessage] | None:
    ...
    user_msg = await self.msg_repo.create(channel="ideation", ...)
    await self._broadcast_msg(proposal_id, user_msg)
    await self._enqueue(
        "run_ideation", proposal_id, idempotency_key=str(user_msg.id),
    )
    return [user_msg]
```

## System prompt construction

```python
def _build_ideation_system_prompt(proposal) -> str:
    sections = [_IDEATION_SYSTEM_PREAMBLE]
    sections.append("## What's known about this proposal so far\n")
    sections.append(f"**Project name:** {proposal.project_name}")
    sections.append(f"**Current phase:** {proposal.pipeline_state.get('current_phase', 'brief')}")

    if proposal.brief:
        sections.append(f"\n**Brief:**\n```json\n{json.dumps(proposal.brief, indent=2)}\n```")
    else:
        sections.append("\n**Brief:** Not yet established — the user hasn't completed brief intake.")

    if proposal.research:
        sections.append(f"\n**Research findings:**\n{_truncate(proposal.research, 3000)}")
    if proposal.benchmarks:
        sections.append(f"\n**Market benchmarks:**\n{_truncate(proposal.benchmarks, 2000)}")

    if proposal.cost_model:
        cm = proposal.cost_model
        sections.append(
            f"\n**Cost model summary:** Total ₹{cm.get('grand_total', 0):,}, "
            f"{len(cm.get('line_items', []))} line items."
        )

    if proposal.covering_letter:
        sections.append(f"\n**Covering letter (current draft):**\n{_truncate(proposal.covering_letter, 1500)}")
    if proposal.executive_summary:
        sections.append(f"\n**Executive summary:**\n{_truncate(proposal.executive_summary, 1500)}")

    return "\n".join(sections)
```

The preamble (`_IDEATION_SYSTEM_PREAMBLE`):

```
You are NUPROP's ideation copilot — a thinking partner for a senior BD lead
at a design / professional-services agency.

The user has an open proposal and wants to think out loud with you about it.
You should:
- Ask probing questions, suggest angles, surface assumptions.
- Reference what's already known about this proposal (below) when helpful.
- Be honest about trade-offs, not just agreeable.
- Keep responses tight and conversational — this is a brainstorm, not a deck.
- Never fabricate facts; if you don't know something, say so.

You can see what the agency has produced so far, but you cannot modify it.
If the user wants to apply your suggestions, they'll do that themselves in
the main proposal flow.
```

### Truncation cutoffs (first-pass)

| Field | Cutoff |
|-------|--------|
| `research` | 3,000 chars |
| `benchmarks` | 2,000 chars |
| `covering_letter` | 1,500 chars |
| `executive_summary` | 1,500 chars |

Truncation is mid-content with a `... (truncated)` marker so Claude knows
content was cut. These are first-pass guesses; tune based on real usage.

For a brand-new proposal (no brief, no research, no narrative) the system
prompt is ~250–300 tokens. For a fully-built proposal it can reach 6,000–8,000
tokens — well within Sonnet 4.6's context.

## Prompt caching

The proposal-context portion of the system prompt is a strong cache target:

- **Stable across turns** of the same ideation conversation — the proposal
  doesn't change while the user is in the drawer (and if it does, the next
  ideation turn rebuilds the prompt and invalidates the old cache entry, as
  intended).
- **Above the 1024-token minimum** for any proposal with at least a brief +
  research populated.

The system block is passed as a list with `cache_control: ephemeral`:

```python
system=[{
    "type": "text",
    "text": _build_ideation_system_prompt(proposal),
    "cache_control": {"type": "ephemeral"},
}]
```

For brand-new proposals where the system prompt is under 1024 tokens,
Bedrock silently bypasses the cache — the call still succeeds, it just
doesn't cache. No special handling needed.

**Expected impact** for a multi-turn brainstorm on a developed proposal:
- Turn 1: full input tokens billed; cache populated; ~3–5s
- Turn 2+: ~85% input-token cost reduction; ~1s faster TTFT; ~2–4s total

## Model tier

`Tier.BALANCED` → Sonnet 4.6 → `global.anthropic.claude-sonnet-4-6`.

- Haiku (FAST) doesn't reason deeply enough about strategic trade-offs — it
  tends to summarise rather than push back.
- Opus (HEAVY) is overkill for chat; ~3× slower and ~5× more expensive per
  token. Save it for cases like narrative generation where the quality
  difference is visible.

If we later expose a tier toggle, the API accepts an optional `tier` body
field; the worker resolves it through the existing tier→model map.

## Frontend

### Entry point

`<IdeateButton />` in the proposal page header — always visible, no phase
gating. Lightbulb icon, subtle treatment (matches existing header nav
weight). An optional unread badge if new ideation messages arrived while the
drawer was closed; unread state is **local-only** (computed client-side from
the last-seen message timestamp in localStorage), not server-side.

### Drawer

`<IdeationDrawer />` — slides in from the right.

- Desktop: **40% viewport width, max 560px**.
- Mobile (< 640px): full-screen modal sliding up from bottom.
- Open state persists in URL hash (`#ideate`), so refresh keeps it open and
  the URL is shareable.
- Dismiss: X button in drawer header, Esc key, click on the dark overlay
  behind the drawer.
- The main chat behind the drawer **dims** (semi-transparent overlay) to
  signal focus, but remains visible (the proposal may be running phases in
  parallel; the user wants to see that).

### Layout

```
┌────────────────────────────────────────────────────┐
│  💡 Ideation                                    [X]│
│  Talking through this proposal with Claude.        │
│  Read-only — nothing here modifies the main flow.  │
├────────────────────────────────────────────────────┤
│                                                    │
│   [message bubble]                                 │
│   [message bubble]                                 │
│   [typing indicator]                               │
│                                                    │
├────────────────────────────────────────────────────┤
│   [chat input ──────────────────────────] [send]   │
└────────────────────────────────────────────────────┘
```

- Header strip: title + the one-line read-only caveat.
- Message list: reuses `MessageBubble` for content rendering. Bubble palette
  is cooler (slate-blue) than the main chat (warm stone) to visually
  differentiate the two contexts.
- Input: same `<ChatInput />` component as the main chat.

### Empty state (first time the drawer opens on a proposal)

```
💡 Think out loud about this proposal.

I can see everything the agency has put together so far — the brief,
research, costing, narrative — but I won't change any of it. Use me to
surface assumptions, try different angles, or stress-test the strategy
before you send it.

Try asking:
  • "What angle should we lead with?"
  • "What would a retainer version of this look like?"
  • "What objections might the client have?"
  • "If we cut the budget by 30%, what would we drop?"
```

The four suggestion lines are clickable — clicking inserts the suggestion
into the chat input but does **not** auto-send (gives the user a chance to
edit before sending).

### Loading / failure states

- **Loading**: reuse the existing `<TypingIndicator />` from the main chat.
- **Failure**: an inline error block in the thread, not a toast.
  ```
  ⚠ Couldn't reach Bedrock — invalid_request_error.
     Send another message to try again.
  ```
  No retry button. The user re-prompts.

### WebSocket integration

The frontend chat store (Zustand) inspects each incoming WS message's
`channel` field on the payload's `message` envelope:

- `channel === "main"` → existing main-thread state slice
- `channel === "ideation"` → new ideation-thread state slice

One WS connection per proposal (keyed by proposal_id); two state slices, two
views. Backwards compatible: existing payloads default to `channel="main"`.

### State scope

| State | Where | Persists across |
|-------|-------|-----------------|
| Drawer open / closed | URL hash | refresh |
| Drawer width | not stored | — |
| Scroll position within thread | not stored | — |
| Unread count | localStorage (last-seen timestamp) | refresh, not across browsers |
| Thread messages | server-side DB | everywhere |

## Test strategy

### Backend

- **Repository test:** `list_by_proposal(channel="ideation")` returns only
  ideation messages; default arg returns only main messages.
- **`IdeationService.run_ideation`:**
  - Persists assistant message with `channel="ideation"` and commits **before**
    publishing — verified by a spy on `publish` that re-reads the row from a
    fresh session inside the spy callback.
  - Loads conversation history filtered to the ideation channel — verified by
    constructing both main and ideation messages on the same proposal and
    asserting the LLM call receives only the ideation history.
  - System prompt construction works for an empty proposal (no brief, no
    research) and for a fully-developed proposal.
- **API endpoints:**
  - `GET /chat/{id}/ideation/messages` returns only ideation rows; cross-agency
    request 404s.
  - `POST /chat/{id}/ideation/send` returns `[user_msg]`, enqueues
    `run_ideation` with a job_id including the user_msg.id suffix, and sets the
    user message's `channel` to `ideation`.
- **Failure path:** when the worker's `run_ideation` raises, a `system`/`error`
  message lands in the ideation channel; `proposal.pipeline_state` is **not**
  modified.
- **Isolation property:** running `run_ideation` does not change any of
  `proposal.brief`, `proposal.research`, `proposal.cost_model`,
  `proposal.covering_letter`, `proposal.pipeline_state` — asserted via a
  before/after fingerprint of those fields.

### Frontend

- **Drawer rendering:** opens via the header button; closes via X, Esc, and
  overlay click.
- **URL hash sync:** opening sets `#ideate`; closing clears it; refresh with
  the hash present keeps the drawer open.
- **Empty state suggestion clicks:** clicking a suggestion fills the chat
  input but does not auto-send.
- **Channel routing:** a mocked WS message with `channel="ideation"` lands in
  the drawer state slice, not the main state slice; vice versa for `"main"`.
- **Send flow:** clicking send posts to `/chat/{id}/ideation/send` and pushes
  the user message into the drawer immediately.
- **Inline error rendering:** a `role=system, type=error` ideation message
  renders as an error block, not a normal bubble.

## Open questions

1. **`IdeationService` as a separate class, or another method on `PipelineService`?**
   The data flow is similar to the existing phases but the read-only invariant
   matters enough that I lean toward a separate class — it makes the "can't
   write to proposal fields" property visible in the type system (the class
   simply doesn't have `proposal_repo.update` in its closure). Plan-stage
   decision; doesn't affect the data model or the API contract.

2. **Drawer dims main chat — or not?** The spec proposes dimming. An
   alternative is a true two-column view where both panels are equally
   visible. Dimming is the safer default (clear focus); easy to revisit after
   real usage.

3. **Should the worker emit a `progress` event when ideation starts** (so the
   drawer shows "typing..." sooner), or rely on the existing `typing`
   broadcast from `send_ideation_message`? The latter is simpler and what
   we'd ship; first-turn TTFT is bounded by Bedrock anyway.

## Self-review

- **Placeholder scan:** no TBDs or TODOs in normative sections. Open questions
  are explicitly called out as deferred decisions.
- **Internal consistency:** read-only invariant (Goals, Architecture, Failure
  isolation, Worker, Tests) is consistent. Same job_id suffix pattern across
  brief intake and ideation. Single-table data model consistent everywhere.
- **Scope check:** the v1 surface is small — one column, one worker phase,
  two endpoints, one frontend drawer. v2 list is explicit and isolated.
- **Ambiguity check:** truncation cutoffs are specific numbers; the prompt
  preamble is verbatim; the WS routing rule is unambiguous (`channel` field).
  The one place a reader could go either way is "separate `IdeationService`
  class vs. another method on `PipelineService`" — explicitly listed as an
  open question for the plan stage.

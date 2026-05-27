# Post-S10 Stability + Chat Intent — Consolidated Spec

**Status:** Drafted 2026-05-27 (end of marathon ops session). Captures every distinct bug, polish item, and feature gap surfaced during today's S10 + post-S10 smoke testing. Ranked by priority and grouped into bite-sized execution slices.
**Goal:** One coherent next-session slice that closes out the operational debt accumulated today AND ships the chat-intent feature (Path B) the user asked for repeatedly.

---

## Why this is a slice, not a list

Today's session exposed ~15 distinct issues across infra, model routing, chat UX, and quality. Some are 5-line fixes; some are real features. Lumping them into one PR would be unreviewable; shipping them one-at-a-time over multiple sessions creates context-loss tax. The right shape is **one slice with four committed sub-deliverables**:

1. **Pipeline reliability hardening** — close the retry traps and silent-failure footguns
2. **Chat intent (Path B)** — the LLM-routed NL → phase trigger
3. **Visible progress UX** — surface "what's happening" while phases run
4. **Cleanup + docs** — CLAUDE.md alignment, HANDOFF tidy, Upstash deletion

Total effort: **~1.5 days** with subagent-driven execution. Each sub-deliverable independently mergeable.

---

## Problem inventory

Each row: ID • Title • Root cause • Proposed fix • Effort • Status. Status is one of:
- `FIXED-TODAY` — landed in today's session; no further action needed
- `OPEN` — needs work
- `EXTERNAL` — operator/vendor action, not code

### Group A — Already fixed today (reference only)

| ID | Title | Status |
|---|---|---|
| A1 | Upstash Redis monthly quota hit — migrated to self-hosted `nuprop-redis` Fly app | `FIXED-TODAY` |
| A2 | Opus 4.7 access denied on this AWS account — swapped heavy tier to Opus 4.6 | `FIXED-TODAY` |
| A3 | Opus 4.6 doesn't accept `web_search` tool on Bedrock — swapped to Sonnet 4.6 | `FIXED-TODAY` (superseded by A4) |
| A4 | Bedrock in `ap-northeast-1` doesn't expose Anthropic's hosted `web_search_20250305` at all — routed `synthesize_research` to direct Anthropic API (Option 1) | `FIXED-TODAY` |
| A5 | ARQ `_job_id` retry trap silently no-ops retries after failure — `_enqueue_phase_job` now DELs result key before enqueueing | `FIXED-TODAY` (gate-approval path only — see P2) |
| A6 | Chat input bubble sluggish (auto-grow textarea forces sync layout per keystroke) — wrapped in `requestAnimationFrame` | `FIXED-TODAY` |
| A7 | `build_cost_model` crashed on `None.package_name[:40]` — defensive `(unmatched)` fallback | `FIXED-TODAY` |
| A8 | `regenerate_section` / `refine_section` were wiping `assets: []` on every call — preserve assets via merge | `FIXED-TODAY` (S10 final-review fix) |
| A9 | Hosted-asset URLs were leaking into the DB instead of being re-signed on read — fixed in `commit_asset` | `FIXED-TODAY` (S10 final-review fix) |
| A10 | S10's IDOR via crafted `s3_key` in `commit_asset` — three defence-in-depth checks added | `FIXED-TODAY` (S10 final-review fix) |

### Group B — Quick wins (each <30 min)

| ID | Title | Root cause | Proposed fix | Effort |
|---|---|---|---|---|
| **P1** | Fly worker process auto-stops after every `fly secrets set` and doesn't auto-restart | `min_machines_running` in `fly.toml` is scoped to `processes = ['app']`; the worker has no equivalent guarantee and no HTTP traffic to wake it. | Add a post-deploy step in `.github/workflows/deploy.yml` that runs the worker-restart `jq` one-liner already documented in HANDOFF § 5b. Catches both `fly deploy` and `fly secrets set` paths. | 15 min |
| **P2** | ARQ `_job_id` retry trap STILL bites in the worker's `_NEXT_PHASE` chaining | `workers/pipeline.py:78` uses raw `ctx["redis"].enqueue_job(...)` with deterministic `_job_id`, NOT the `_enqueue_phase_job` helper that has the DEL fix. So if `run_benchmarks` fails after `run_research` chains it, retry silently no-ops. | Refactor the chain in `_run_phase` to DEL the result key before enqueueing the next phase. Add a regression test. | 20 min |
| **P3** | `CLAUDE.md` global instruction still says "always route through AWS Bedrock; never use ANTHROPIC_API_KEY" — contradicts today's Option 1 swap | Policy was written before hosted-tool capabilities; the carve-out for hosted-tool calls wasn't anticipated. | Edit `~/.claude/CLAUDE.md` to add the exception: "Hosted-tool calls (web_search, web_fetch, code_execution) that Bedrock doesn't proxy route to AsyncAnthropic. Everything else via Bedrock." | 5 min |
| **P4** | `process_stream` doesn't extract citations from Anthropic's hosted `web_search` response shape — body has inline source mentions but `extra_data.citations == []` | Either the SDK response shape changed since `process_stream` was written, OR hosted-tool citations come through a different content block type than expected. | Capture a real response (today's `benchmarks_findings` saved an example), inspect the actual block shape, update the extraction logic in `research_streaming.py:151+`. | 30 min |
| **P5** | Standby worker `865139be669de8` is unnecessarily running (Fly secret rotation woke it up; now duplicates queue polling against the primary) | Fly auto-starts ALL machines in a process group on secret rotation, even the standby. ARQ handles concurrent workers safely, but it's wasteful. | `fly machine stop 865139be669de8 -a nuprop`. One-line operator action. | 1 min (`EXTERNAL`) |
| **P6** | App machine on version 42, workers on version 43 — version skew from today's failed-then-retried deploy | Fly capacity issue in `bom` blocked the app-machine update during the secret rotation; the workers came up cleanly. | `fly machine update 48e71eea0119e8 -a nuprop --restart-only` (retry when `bom` has capacity). | 2 min (`EXTERNAL`) |
| **P7** | Upstash subscription still active after self-host migration | Need to cancel after 24h verification window | Cancel in Upstash console + delete `positive-man-126512` database | 2 min (`EXTERNAL`) |

### Group C — Real features (~half-day each)

| ID | Title | Root cause | Proposed fix | Effort |
|---|---|---|---|---|
| **P8** | **Chat doesn't understand typed phase requests** ("run the benchmark again" → echo stub) — the user's most consistently re-flagged complaint | `chat_viewmodel.send_message` has AI behavior ONLY in the `brief` phase; every other phase short-circuits to `_echo_response`. There's no NLU, no slash commands, no intent detection. | **Path B: LLM-routed intent classifier** — see "Path B design" section below. | 4-5 h |
| **P9** | No visible progress while research / benchmarks / sections run | Activity log is the only signal, and it's inside the chat — easy to miss. No persistent "phase X is running" indicator. WS `typing` events exist but the UI only renders them as a small "AI is thinking" footer. | Add a persistent **PhaseProgress** widget at the top of the chat (sticky), showing: phase name, status (queued/running/complete/failed), elapsed time, and any progress hints from the activity log. WS messages already carry enough state; this is a frontend-only feature. | 3 h |
| **P10** | Failed-phase retry isn't surfaced in the UI | The `/retry` endpoint exists but the chat has no button to call it; users have to know to hit it via DevTools. | Add a "**Retry**" button to the chat-message rendering for any message with `extra_data.status == "failed"`. Calls `/chat/{id}/retry`. | 1 h |
| **P11** | `CostModelBuilder` produces line items with `package_name=None` on the fallback path | Deliverable doesn't match any rate-card entry → CostModelBuilder uses a fallback rate but doesn't synthesize a package label. Today's defensive fix in pipeline_service masks the symptom. | Either: (a) have CostModelBuilder synthesize a `package_name` like `"Custom ({deliverable.category})"` for fallback items, OR (b) expose the "unmatched" state cleanly in the cost-model card so the user can search/add a matching rate. (a) is simpler and more honest. | 1 h |

### Group D — Polish / nice-to-have (defer if scope creeps)

| ID | Title | Effort |
|---|---|---|
| P12 | S10 `AddImageMenu` lacks click-outside-to-close on the dropdown | 30 min |
| P13 | S10 lost-update race on section JSON column (read-modify-write pattern) — pre-existing, exists in `patch_section` too | 2 h (atomic JSONB `||` append in Postgres) |
| P14 | S10 hosted-tool error path: `generate_image` raises bare `RuntimeError` on fal.ai content-policy block — already translates to 502 but error message is opaque | 30 min |
| P15 | S13 (persistent client-context chip + Gmail thread picker) — a whole slice the user flagged at the start of today | ~1 week (entirely separate; not part of this consolidation) |

---

## Path B design — LLM-routed chat intent

Replacing the `_echo_response` placeholder with a proper intent layer. Architectural decisions locked here so the implementer doesn't re-litigate.

### Scope (what's in)

When the user types a message OUTSIDE the brief phase, classify intent into one of these buckets and route accordingly:

| Intent | Backend action | UI feedback |
|---|---|---|
| `re_run_phase(phase)` | Enqueue the named phase, clear stale result key | "Re-running research..." |
| `regenerate_section(section_type)` | Call existing `/sections/{type}/regenerate` | "Regenerating problem statement..." |
| `refine_section(section_type, instructions)` | Call existing `/sections/{type}/refine` | "Refining cover page based on your input..." |
| `edit_cost_item(deliverable, field, value)` | Call existing `/chat/{id}/cost-model` patch | "Updated quantity for Logo to 2." |
| `ask_question` | Single Sonnet 4.6 turn: answer using the proposal's brief + research + sections as context | Plain assistant chat message |
| `unknown` | Fall back to clarification message: "I can re-run research, regenerate a section, refine a section's content, edit cost items, or answer questions. Try: 'redo research' or 'regenerate problem statement'." | Static help message |

### Out of scope (defer)

- Multi-turn planning ("first re-run research, THEN regenerate the cover page") — too complex; phase-1 handles single-action intents only
- Generating new section types beyond the 9 canonical ones
- Modifying brief / template after initial intake (would require a separate "reset" flow)
- Voice input / file attachments

### Implementation shape

**New file: `backend/app/services/ai/chat_intent.py`** — ~120 lines

```python
"""LLM-routed chat intent classifier.

Single Haiku 4.5 call per non-brief user message. Returns a structured
Intent dict; the chat viewmodel routes based on intent.kind. Kept dependency-
free of routing logic so the test surface stays tight.

Cost: ~$0.0002 per classification (Haiku 4.5 is cheap). Latency: ~500ms p50.
"""

from typing import Literal, TypedDict

class Intent(TypedDict):
    kind: Literal[
        "re_run_phase", "regenerate_section", "refine_section",
        "edit_cost_item", "ask_question", "unknown",
    ]
    # kind-specific payload
    phase: str | None             # for re_run_phase
    section_type: str | None      # for regenerate_section, refine_section
    instructions: str | None      # for refine_section
    deliverable: str | None       # for edit_cost_item
    field: str | None             # for edit_cost_item: "quantity" or "unit_cost"
    value: int | None             # for edit_cost_item
    question: str | None          # for ask_question
    confidence: float             # 0.0-1.0; below 0.6 → kind="unknown"

async def classify_intent(
    *,
    user_message: str,
    current_phase: str,
    proposal_state_hint: dict,
) -> Intent:
    """Single Haiku call. System prompt enumerates the intent kinds + few-shot
    examples. JSON schema validation on the response."""
```

**System prompt** sketches:
- Identify the user's intent from one of 6 categories
- Extract typed payload (which phase, which section, etc.)
- Return a confidence score
- Few-shot: 8-10 examples covering common variations ("redo research", "rerun benchmark", "regen cover page", "make problem statement shorter", "change Logo quantity to 3", "what does my cost model show?")

**Routing in `ChatViewModel.send_message`** replaces the current echo:

```python
# Replace the current "non-brief phases: echo placeholder" block
intent = await classify_intent(
    user_message=content,
    current_phase=current_phase,
    proposal_state_hint={
        "has_sections": proposal.cover_page is not None,
        "section_types": [...],
        "cost_model_items": [...],
    },
)
return await self._dispatch_intent(proposal, intent, user_msg)
```

`_dispatch_intent` is a switch on `intent["kind"]` that calls the appropriate enqueue / endpoint / inline LLM call and creates an ack message.

### Tests

- Unit test for classify_intent with mocked Haiku, covering all 6 kinds + a clearly unknown case
- Integration test for send_message → classify_intent → enqueue, covering re_run_phase + regenerate_section
- Edge cases: empty message, gibberish, phase that doesn't exist ("rerun the doodad")

### UX considerations

- Show "Thinking..." spinner during classification (~500ms) so users don't think the chat is broken
- After classification, show a brief ack: "Re-running research..." — gives the user confidence before the slow phase work starts
- For `unknown`, show the help message as the response

### Cost ceiling

One Haiku call per non-brief chat message. Haiku 4.5 at ~$0.0002/call. Even at 100 user messages/proposal (extreme), that's $0.02 — rounding error.

---

## Recommended execution order

**Sub-slice 1: Pipeline reliability hardening** (~1.5 h)
- P1 (deploy.yml worker-restart)
- P2 (ARQ chain retry-trap)
- P4 (hosted-tool citation extraction)

**Sub-slice 2: Chat intent — Path B** (~4-5 h)
- P8 (the feature)
- Includes tests + frontend ack rendering

**Sub-slice 3: Visible progress UX** (~3 h)
- P9 (PhaseProgress widget)
- P10 (Retry button on failed messages)

**Sub-slice 4: Quality + cleanup** (~2 h)
- P11 (CostModelBuilder synthesizes fallback package_name)
- P3 (CLAUDE.md edit)
- P5 + P6 + P7 (operator actions; checklist into HANDOFF)
- Update HANDOFF § 5 to close out the items that land in this slice

**Total: ~10-11 h.** Doable in one focused day; comfortably two if reviews are thorough.

---

## Open questions for the user to confirm before execution

1. **Scope of Path B intent classifier** — current design covers 6 intent kinds. Want to add more (e.g., "show me the brief", "what's the status of cost model", "summarize what we've done")? Or keep tight and grow later?
2. **Chat intent fallback model** — Haiku 4.5 (cheap, fast) vs. Sonnet 4.6 (more accurate). I picked Haiku for $/latency; you may want Sonnet for better intent recognition.
3. **PhaseProgress widget placement** — sticky top-of-chat? Floating bottom-right? Side panel? I sketched "sticky top" but it's up to you.
4. **Path B in the same chat or new commands surface?** — current proposal puts intent classification inline (everything goes through chat). Alternative: keep chat as the "type freely" channel + add explicit action buttons (Re-run benchmark, Regenerate section X) elsewhere in the UI. Hybrid possible.

---

## What this slice doesn't include

- S11 (video + audio media via fal.ai)
- S12 (NUSTAGE export + publish + share token)
- S13 (persistent client-context chip + Gmail thread picker)

All three are real features tracked on the section-redesign roadmap and need their own brainstorm-spec-plan cycles. This slice is **stability + chat intent** — closing out what was painful today.

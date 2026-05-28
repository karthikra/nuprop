# Sub-Slice 2: Path B — LLM-Routed Chat Intent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each implementer subagent MUST run the worktree+branch safety check before committing (see "Commit safety" below).

**Goal:** Replace the non-brief-phase `_echo_response` placeholder in chat with a real LLM-routed intent layer: a single Haiku 4.5 classification call routes a free-form user message to one of 6 actions (re-run a phase, regenerate/refine a section, edit a cost item, answer a question, or fall back to help).

**Architecture:** One new classifier module (`chat_intent.py`) does a single `AIService.complete_json` call (Tier.FAST = Haiku 4.5, Bedrock-routed). Before wiring the dispatcher, two pieces of inline route logic are extracted into reusable services (section regeneration, cost-item edit) so the chat dispatcher and the existing REST endpoints share one code path. The dispatcher (`_dispatch_intent` on `ChatViewModel`) switches on the classified intent kind, performs the action, and returns an ack chat message. Backend-only — ack messages render as existing plain `text` bubbles; the "Thinking…" state reuses the existing WS `typing` event.

**Tech Stack:** FastAPI, SQLAlchemy (async), ARQ, AWS Bedrock via `AIService` (`app/services/llm.py`), pytest + pytest-asyncio.

**Source spec:** `docs/superpowers/specs/2026-05-27-post-s10-stability-and-chat-intent.md` Group C item P8 + the "Path B design" section. **Locked decisions** (from user, 2026-05-28): 6 intents (tight), Haiku 4.5 classifier, hybrid action surface (buttons come in sub-slice 3), sticky-top PhaseProgress (sub-slice 3).

---

## Commit safety (every implementer subagent MUST do this)

A prior subagent accidentally committed to `main` in the original checkout. Before ANY `git commit`, verify:
```
git rev-parse --show-toplevel    # MUST end with /.claude/worktrees/post-s10-stability-and-chat-intent
git branch --show-current        # MUST be: worktree-post-s10-stability-and-chat-intent
```
STOP/report BLOCKED if either fails. NEVER run git against `/Users/karthikramesh/Developer/nuprop`. Stage explicit paths only — never `git add -A`/`git add .`.

---

## Shared facts (true as of this plan; verify if surprising)

**`send_message`** lives at `backend/app/viewmodels/chat_viewmodel.py:95`. Non-brief phases currently hit lines 134-138:
```python
        assistant_msg = await self._echo_response(proposal_id, content, current_phase)
        await self._broadcast_msg(proposal_id, assistant_msg)
        return [user_msg, assistant_msg]
```
`_echo_response` (line ~328) stays as the `unknown`-intent fallback.

**LLM call primitive** — `app/services/llm.py`:
```python
from app.services.llm import Tier, get_ai_service
ai = get_ai_service()
data: dict = await ai.complete_json(prompt, tier=Tier.FAST, system=SYSTEM, max_tokens=256)
```
`complete_json` injects "Return ONLY valid JSON", strips fences, `json.loads`. `Tier.FAST` = `global.anthropic.claude-haiku-4-5-20251001-v1:0`. `Tier.BALANCED` = Sonnet 4.6 (used for `ask_question`).

**`current_phase` values:** `brief`, `template_confirm`, `rate_card_gaps`, `research`, `cost_model_review`, `sections`, `section_editor`.

**ARQ job names:** `analyze_brief`, `run_research`, `run_benchmarks`, `build_cost_model`, `generate_sections`. No phase→job table exists yet — Task 4 adds one.

**9 canonical sections** (`app/services/sections/__init__.py`): `cover_page`, `executive_summary`, `problem_statement`, `proposed_solution`, `scope_of_work`, `timeline`, `pricing`, `qualifications`, `terms_and_conditions`. `SYNTHESIS_SECTIONS = {cover_page, executive_summary}`; `FACT_SECTIONS` = the other 7. `SECTION_ORDER` is the validation list; `_validate_section_type` raises 400 for unknowns.

**Cost-model edit** — `PATCH /chat/{id}/cost-model`, body `{index:int, field:"quantity"|"unit_cost", value:int}`. Logic inline at `chat.py:139-196`: update `item[field]`, recalc `item.total = unit_cost*quantity`, then recalc `subtotal`/`discount_amount`/`total`/`gst_amount`(18%)/`grand_total`; persist; broadcast `{"type":"cost_model_update","cost_model":...}`.

**Section regen** — `_generate_section(proposal, section_type, refine_instructions, db)` in `proposals.py:598`, called by both `regenerate_section` (POST, no body) and `refine_section` (POST, body `{instructions:str}`). Dispatches to `generate_fact_section` / `generate_synthesis_section` in `app/services/sections/`.

**Ack creation** (API-process, synchronous):
```python
ack = await self.msg_repo.create(
    proposal_id=proposal_id, role=MessageRole.ASSISTANT.value,
    message_type=MessageType.TEXT.value, content="Re-running research…", phase=current_phase,
)
await self._broadcast_msg(proposal_id, ack)
```

**Typing indicator:** broadcast a `typing` WS event before the slow classify/dispatch; an arriving `new_message` clears it on the frontend. Mirror the brief-phase typing pattern at `chat_viewmodel.py:122-132`.

**Test mocking caveat:** the autouse `_no_network` fixture patches `AnthropicClient` but NOT `AIService`. Classifier/dispatch tests MUST monkeypatch `AIService.complete_json` (or patch `classify_intent` at the viewmodel call site). The standard fixtures are `client, registered, arq_pool, make_proposal_api, db, make_proposal_db, monkeypatch`.

---

## File map

**Create:**
- `backend/app/services/ai/chat_intent.py` — the classifier + `Intent` model + `PHASE_TO_JOB` map
- `backend/app/services/sections/regeneration.py` — extracted reusable section-regen function (Task 2)
- `backend/app/services/cost_model_service.py` — extracted reusable cost-item-edit function (Task 3)
- `backend/tests/unit/test_chat_intent.py`
- `backend/tests/integration/test_chat_intent_dispatch.py`

**Modify:**
- `backend/app/views/v1/proposals.py` — `_generate_section` delegates to the new regeneration service (Task 2)
- `backend/app/views/v1/chat.py` — cost-model PATCH handler delegates to the new cost-model service (Task 3)
- `backend/app/viewmodels/chat_viewmodel.py` — add `_dispatch_intent`, wire into `send_message` (Task 4)

---

## Task 1: Intent classifier module + unit tests

**Files:**
- Create: `backend/app/services/ai/chat_intent.py`
- Test: `backend/tests/unit/test_chat_intent.py`

### Step 1: Write the failing unit tests

- [ ] Create `backend/tests/unit/test_chat_intent.py`:

```python
"""Unit tests for the LLM-routed chat-intent classifier.

The classifier makes a single Haiku 4.5 call (Tier.FAST) via AIService and
returns a normalized Intent dict. These tests mock AIService.complete_json
(the global _no_network guard only blocks AnthropicClient, not AIService) so
no real Bedrock call is made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.ai import chat_intent
from app.services.ai.chat_intent import Intent, classify_intent


def _hint():
    return {
        "section_types": ["problem_statement", "cover_page", "pricing"],
        "cost_items": ["Logo", "Brand Guidelines"],
    }


async def _run(monkeypatch, raw: dict) -> Intent:
    monkeypatch.setattr(
        "app.services.ai.chat_intent.get_ai_service",
        lambda: AsyncMock(complete_json=AsyncMock(return_value=raw)),
    )
    return await classify_intent(
        user_message="x", current_phase="cost_model_review",
        proposal_state_hint=_hint(),
    )


@pytest.mark.asyncio
async def test_re_run_phase(monkeypatch):
    intent = await _run(monkeypatch, {
        "kind": "re_run_phase", "phase": "research", "confidence": 0.95,
    })
    assert intent["kind"] == "re_run_phase"
    assert intent["phase"] == "research"


@pytest.mark.asyncio
async def test_regenerate_section(monkeypatch):
    intent = await _run(monkeypatch, {
        "kind": "regenerate_section", "section_type": "problem_statement",
        "confidence": 0.9,
    })
    assert intent["kind"] == "regenerate_section"
    assert intent["section_type"] == "problem_statement"


@pytest.mark.asyncio
async def test_refine_section(monkeypatch):
    intent = await _run(monkeypatch, {
        "kind": "refine_section", "section_type": "cover_page",
        "instructions": "make it punchier", "confidence": 0.88,
    })
    assert intent["kind"] == "refine_section"
    assert intent["instructions"] == "make it punchier"


@pytest.mark.asyncio
async def test_edit_cost_item(monkeypatch):
    intent = await _run(monkeypatch, {
        "kind": "edit_cost_item", "deliverable": "Logo",
        "field": "quantity", "value": 3, "confidence": 0.9,
    })
    assert intent["kind"] == "edit_cost_item"
    assert intent["deliverable"] == "Logo"
    assert intent["field"] == "quantity"
    assert intent["value"] == 3


@pytest.mark.asyncio
async def test_ask_question(monkeypatch):
    intent = await _run(monkeypatch, {
        "kind": "ask_question", "question": "what's my grand total?",
        "confidence": 0.8,
    })
    assert intent["kind"] == "ask_question"
    assert intent["question"]


@pytest.mark.asyncio
async def test_low_confidence_becomes_unknown(monkeypatch):
    """Below the 0.6 threshold the classifier downgrades to unknown so the
    dispatcher shows help rather than acting on a bad guess."""
    intent = await _run(monkeypatch, {
        "kind": "re_run_phase", "phase": "research", "confidence": 0.3,
    })
    assert intent["kind"] == "unknown"


@pytest.mark.asyncio
async def test_unparseable_model_output_becomes_unknown(monkeypatch):
    """If the model returns a kind we don't recognize, fall back to unknown
    rather than raising into the chat send path."""
    intent = await _run(monkeypatch, {"kind": "delete_everything", "confidence": 0.99})
    assert intent["kind"] == "unknown"


@pytest.mark.asyncio
async def test_invalid_field_for_edit_cost_item_becomes_unknown(monkeypatch):
    """edit_cost_item must carry field in {quantity, unit_cost}; anything else
    is unsafe to act on."""
    intent = await _run(monkeypatch, {
        "kind": "edit_cost_item", "deliverable": "Logo",
        "field": "color", "value": 3, "confidence": 0.9,
    })
    assert intent["kind"] == "unknown"


@pytest.mark.asyncio
async def test_llm_exception_becomes_unknown(monkeypatch):
    """A Bedrock/JSON failure must degrade to unknown, never 500 the chat send."""
    monkeypatch.setattr(
        "app.services.ai.chat_intent.get_ai_service",
        lambda: AsyncMock(complete_json=AsyncMock(side_effect=ValueError("bad json"))),
    )
    intent = await classify_intent(
        user_message="x", current_phase="research", proposal_state_hint=_hint(),
    )
    assert intent["kind"] == "unknown"
```

### Step 2: Run tests — expect failures

Run: `cd backend && uv run pytest tests/unit/test_chat_intent.py -v`
Expected: ImportError / failures (module not yet created).

### Step 3: Implement the classifier

- [ ] Create `backend/app/services/ai/chat_intent.py`:

```python
"""LLM-routed chat-intent classifier.

A single Haiku 4.5 call (Tier.FAST, Bedrock-routed via AIService) maps a
free-form user message — sent outside the `brief` phase — to one of six
intent kinds. The chat viewmodel routes on `intent["kind"]`. Kept free of any
routing logic so the test surface stays tight (mock AIService.complete_json).

Cost: ~$0.0002 per classification. Any failure (Bedrock error, bad JSON,
unrecognized kind, low confidence) degrades to kind="unknown" so a bad guess
can never 500 the chat send or trigger the wrong action.
"""

from __future__ import annotations

import logging
from typing import Literal, TypedDict

from app.services.llm import Tier, get_ai_service

logger = logging.getLogger(__name__)

IntentKind = Literal[
    "re_run_phase", "regenerate_section", "refine_section",
    "edit_cost_item", "ask_question", "unknown",
]

# Normalized phase vocabulary the classifier may emit for re_run_phase,
# mapped to the ARQ job that runs it. This is the single source of truth for
# "user-facing phase keyword" -> "ARQ job name".
PHASE_TO_JOB: dict[str, str] = {
    "research": "run_research",
    "benchmarks": "run_benchmarks",
    "cost_model": "build_cost_model",
    "sections": "generate_sections",
}

_CONFIDENCE_FLOOR = 0.6
_VALID_COST_FIELDS = {"quantity", "unit_cost"}


class Intent(TypedDict, total=False):
    kind: IntentKind
    phase: str | None
    section_type: str | None
    instructions: str | None
    deliverable: str | None
    field: str | None
    value: int | None
    question: str | None
    confidence: float


def _unknown() -> Intent:
    return {"kind": "unknown", "confidence": 0.0}


_SYSTEM = """You classify a user's chat message in a proposal-building app into ONE intent.

The user is past the initial brief and is iterating on a generated proposal. Pick the single best intent and extract its payload. Return JSON only.

Intent kinds and their payload fields:
- "re_run_phase": user wants to re-run a pipeline phase. Field `phase` ∈ {research, benchmarks, cost_model, sections}.
- "regenerate_section": user wants a section regenerated from scratch. Field `section_type` (one of the available sections).
- "refine_section": user wants a section adjusted with guidance. Fields `section_type` and `instructions` (the user's guidance, verbatim-ish).
- "edit_cost_item": user wants to change a cost line item. Fields `deliverable` (the item name), `field` ∈ {quantity, unit_cost}, `value` (integer).
- "ask_question": user is asking a question about the proposal. Field `question`.
- "unknown": none of the above, or ambiguous.

Always include a `confidence` float in [0,1]. If unsure, prefer "unknown" or a low confidence.

Examples:
"redo the research" -> {"kind":"re_run_phase","phase":"research","confidence":0.97}
"run the benchmark again" -> {"kind":"re_run_phase","phase":"benchmarks","confidence":0.95}
"regenerate the problem statement" -> {"kind":"regenerate_section","section_type":"problem_statement","confidence":0.95}
"make the cover page punchier" -> {"kind":"refine_section","section_type":"cover_page","instructions":"make it punchier","confidence":0.9}
"change the Logo quantity to 3" -> {"kind":"edit_cost_item","deliverable":"Logo","field":"quantity","value":3,"confidence":0.93}
"what's my grand total?" -> {"kind":"ask_question","question":"what's my grand total?","confidence":0.85}
"asdfgh" -> {"kind":"unknown","confidence":0.0}
"""


async def classify_intent(
    *,
    user_message: str,
    current_phase: str,
    proposal_state_hint: dict,
) -> Intent:
    """Single Haiku call. Returns a normalized Intent; never raises."""
    section_types = proposal_state_hint.get("section_types") or []
    cost_items = proposal_state_hint.get("cost_items") or []
    prompt = (
        f"Current phase: {current_phase}\n"
        f"Available sections: {', '.join(section_types) or '(none yet)'}\n"
        f"Cost line items: {', '.join(cost_items) or '(none yet)'}\n\n"
        f"User message:\n{user_message}"
    )
    try:
        raw = await get_ai_service().complete_json(
            prompt, tier=Tier.FAST, system=_SYSTEM, max_tokens=256,
        )
    except Exception:  # noqa: BLE001 — any failure degrades to unknown
        logger.exception("chat intent classification failed; defaulting to unknown")
        return _unknown()

    if not isinstance(raw, dict):
        return _unknown()

    kind = raw.get("kind")
    valid_kinds = {
        "re_run_phase", "regenerate_section", "refine_section",
        "edit_cost_item", "ask_question", "unknown",
    }
    if kind not in valid_kinds:
        return _unknown()

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if kind != "unknown" and confidence < _CONFIDENCE_FLOOR:
        return _unknown()

    # Per-kind payload validation — reject anything we can't safely act on.
    if kind == "re_run_phase" and raw.get("phase") not in PHASE_TO_JOB:
        return _unknown()
    if kind in ("regenerate_section", "refine_section") and not raw.get("section_type"):
        return _unknown()
    if kind == "refine_section" and not raw.get("instructions"):
        return _unknown()
    if kind == "edit_cost_item":
        if raw.get("field") not in _VALID_COST_FIELDS:
            return _unknown()
        if not isinstance(raw.get("value"), int) or isinstance(raw.get("value"), bool):
            return _unknown()
        if not raw.get("deliverable"):
            return _unknown()
    if kind == "ask_question" and not raw.get("question"):
        return _unknown()

    intent: Intent = {"kind": kind, "confidence": confidence}
    for f in ("phase", "section_type", "instructions", "deliverable", "field", "value", "question"):
        if f in raw:
            intent[f] = raw[f]
    return intent
```

### Step 4: Run tests — expect green

Run: `cd backend && uv run pytest tests/unit/test_chat_intent.py -v`
Expected: 9 passed.

### Step 5: ruff + commit (after the commit-safety check)

```bash
cd backend && uv run ruff check app/services/ai/chat_intent.py
git add backend/app/services/ai/chat_intent.py backend/tests/unit/test_chat_intent.py
git commit -m "feat(chat): add LLM-routed intent classifier (Haiku 4.5)"
```

---

## Task 2: Extract reusable section-regeneration service

**Why:** The chat dispatcher (Task 4) needs to regenerate/refine a section without importing view-layer code. Currently `_generate_section` lives in `proposals.py` (view layer). Extract its logic into a service the viewmodel and the existing endpoints both call. No behavior change — existing endpoint tests must stay green.

**Files:**
- Read first: `backend/app/views/v1/proposals.py` — the `_generate_section` function (~line 598) and the two endpoints that call it (`regenerate_section` ~371, `refine_section` ~393).
- Create: `backend/app/services/sections/regeneration.py`
- Modify: `backend/app/views/v1/proposals.py` — `_generate_section` becomes a thin delegate.
- Test: existing `backend/tests/integration/test_section_endpoints.py` must stay green.

### Step 1: Read and understand `_generate_section`

- [ ] Read `_generate_section` in full plus the two endpoints. Note its exact signature, what it validates, how it dispatches fact vs synthesis, how it persists, and whether it broadcasts. Preserve ALL of this behavior.

### Step 2: Create the service module

- [ ] Create `backend/app/services/sections/regeneration.py` with a function `regenerate_section_content(*, proposal, section_type, refine_instructions, db)` (match the parameter set `_generate_section` actually uses — adapt names to what you read). Move the body verbatim. It dispatches to `generate_fact_section` / `generate_synthesis_section` based on `section_type in SYNTHESIS_SECTIONS` (or `FACT_SECTIONS` — use whichever the original uses), persists the updated section, and returns the updated section dict (and broadcasts if the original did).

Do NOT change the logic. If the original reads/writes the DB or broadcasts, replicate exactly. If it depends on helpers local to `proposals.py`, either move those too or import them — choose the lower-churn option and note it.

### Step 3: Make `_generate_section` delegate

- [ ] In `proposals.py`, replace the body of `_generate_section` with a call to `regenerate_section_content(...)`, preserving its signature so the two endpoints don't change. Add the import at module top (this file imports infra/services at top — follow that style; do NOT lazy-import).

### Step 4: Run the section endpoint tests

Run: `cd backend && uv run pytest tests/integration/test_section_endpoints.py -v`
Expected: all pass (same count as before). The double-monkeypatch in those tests patches `generate_fact_section` on both its defining module and the `proposals` view module — if your extraction changes WHERE `generate_fact_section` is imported, update the test's second patch target accordingly (and note it). Prefer to keep `generate_fact_section` imported in `regeneration.py` and have the test patch there.

### Step 5: Full suite + ruff + commit

```bash
cd backend && uv run pytest -q && uv run ruff check app/services/sections/regeneration.py app/views/v1/proposals.py
git add backend/app/services/sections/regeneration.py backend/app/views/v1/proposals.py
# include the test file ONLY if you had to update a patch target
git commit -m "refactor(sections): extract section regeneration into a reusable service"
```
Expected suite: previous green count, unchanged (pure refactor; no new tests required here).

---

## Task 3: Extract reusable cost-item-edit service

**Why:** The dispatcher's `edit_cost_item` needs the same recalc logic that's currently inline in the `PATCH /chat/{id}/cost-model` handler. Extract it so both share one path.

**Files:**
- Read first: `backend/app/views/v1/chat.py:139-196` (the `update_cost_item` handler + `UpdateCostItemRequest`).
- Create: `backend/app/services/cost_model_service.py`
- Modify: `backend/app/views/v1/chat.py` — handler delegates to the service.
- Test: existing cost-model tests in `backend/tests/integration/test_chat_api.py` (`test_patch_cost_model_item_recalculates_totals`) must stay green.

### Step 1: Read the handler

- [ ] Read `chat.py:139-196` carefully. Note the exact recalc rules: `item.total = unit_cost * quantity`, `subtotal = sum(item.total)`, `discount_amount`, `total`, `gst_amount` (18%), `grand_total`. Note bounds/validation (index in range, field allowed, line_items exists).

### Step 2: Create the service

- [ ] Create `backend/app/services/cost_model_service.py`:

```python
"""Cost-model mutation helpers shared by the REST PATCH endpoint and the
chat-intent dispatcher. Pure dict-in / dict-out so it's trivially testable and
has no DB or transport coupling.
"""

from __future__ import annotations


_VALID_FIELDS = {"quantity", "unit_cost"}
_GST_RATE = 0.18  # confirm against the handler; use whatever the handler uses


class CostItemEditError(ValueError):
    """Raised when an edit can't be applied (bad index/field/missing model)."""


def apply_cost_item_edit(cost_model: dict, *, index: int, field: str, value: int) -> dict:
    """Return a new/mutated cost_model with one line item edited and all totals
    recalculated. Raises CostItemEditError on invalid input.

    Mirror the recalculation EXACTLY as implemented in the chat.py handler —
    copy the arithmetic, don't reinvent it.
    """
    # IMPLEMENT by transcribing the handler's logic. Pseudocode shape:
    #   validate cost_model has "line_items"; validate field in _VALID_FIELDS;
    #   validate 0 <= index < len(line_items); set item[field]=value;
    #   item["total"]=item["unit_cost"]*item["quantity"]; recompute subtotal,
    #   discount_amount, total, gst_amount, grand_total exactly as the handler does.
    raise NotImplementedError  # replace with the transcribed logic


def find_line_item_index(cost_model: dict, deliverable: str) -> int | None:
    """Case-insensitive match of a deliverable name to its line-item index.
    Used by the chat dispatcher (the classifier emits a name, the editor needs
    an index). Returns None if no match."""
    items = (cost_model or {}).get("line_items") or []
    target = deliverable.strip().lower()
    for i, item in enumerate(items):
        if str(item.get("deliverable", "")).strip().lower() == target:
            return i
    return None
```

IMPORTANT: replace the `NotImplementedError` body by transcribing the handler's actual arithmetic. The two `_VALID_FIELDS`/`_GST_RATE` constants must match the handler. Do not guess the GST rate — read it.

### Step 3: Write the service unit test (TDD for the new behavior)

- [ ] Create `backend/tests/unit/test_cost_model_service.py`:

```python
from __future__ import annotations

import pytest

from app.services.cost_model_service import (
    CostItemEditError, apply_cost_item_edit, find_line_item_index,
)


def _model():
    return {
        "line_items": [
            {"deliverable": "Logo", "quantity": 1, "unit_cost": 100000, "total": 100000},
            {"deliverable": "Brand Guidelines", "quantity": 2, "unit_cost": 50000, "total": 100000},
        ],
        "discount_amount": 0,
    }


def test_edit_quantity_recalculates_item_and_grand_total():
    out = apply_cost_item_edit(_model(), index=0, field="quantity", value=3)
    assert out["line_items"][0]["total"] == 300000
    # grand_total must include 18% GST on the post-discount subtotal.
    # subtotal = 300000 + 100000 = 400000; gst = 72000; grand = 472000
    assert out["grand_total"] == 472000


def test_invalid_field_raises():
    with pytest.raises(CostItemEditError):
        apply_cost_item_edit(_model(), index=0, field="color", value=3)


def test_out_of_range_index_raises():
    with pytest.raises(CostItemEditError):
        apply_cost_item_edit(_model(), index=9, field="quantity", value=3)


def test_find_line_item_index_is_case_insensitive():
    assert find_line_item_index(_model(), "logo") == 0
    assert find_line_item_index(_model(), "BRAND guidelines") == 1
    assert find_line_item_index(_model(), "nope") is None
```

NOTE: the exact `grand_total` assertion (472000) assumes 18% GST and no discount. If the handler's arithmetic differs (e.g., discount applied before GST, rounding), ADJUST the expected number to match the handler's real formula — the test must encode the handler's actual behavior, not an idealized one. Run the test, see the real number, reconcile against the handler logic.

### Step 4: Make the PATCH handler delegate

- [ ] In `chat.py`, replace the inline recalc in the cost-model handler with `apply_cost_item_edit(cost_model, index=..., field=..., value=...)`, translating `CostItemEditError` into the existing `HTTPException` (same status code the handler currently raises — likely 400/422; preserve it). Keep the persist + `cost_model_update` broadcast + return-value behavior identical.

### Step 5: Run cost-model tests

Run:
```
cd backend && uv run pytest tests/unit/test_cost_model_service.py tests/integration/test_chat_api.py -v
```
Expected: new unit tests pass; `test_patch_cost_model_item_recalculates_totals` still passes unchanged.

### Step 6: Full suite + ruff + commit

```bash
cd backend && uv run pytest -q && uv run ruff check app/services/cost_model_service.py app/views/v1/chat.py
git add backend/app/services/cost_model_service.py backend/app/views/v1/chat.py backend/tests/unit/test_cost_model_service.py
git commit -m "refactor(cost-model): extract cost-item edit into a reusable service"
```

---

## Task 4: Dispatcher + send_message wiring + integration tests

**Files:**
- Modify: `backend/app/viewmodels/chat_viewmodel.py` — add `_dispatch_intent`, build `proposal_state_hint`, wire into `send_message`.
- Test: `backend/tests/integration/test_chat_intent_dispatch.py`

### Step 1: Write the failing integration tests

- [ ] Create `backend/tests/integration/test_chat_intent_dispatch.py`:

```python
"""Integration tests for Path B dispatch: a non-brief chat message is
classified and routed to the right action, producing an ack message.

The classifier (AIService.complete_json) is mocked by patching
`classify_intent` at the viewmodel's import site, so these tests exercise the
DISPATCH logic deterministically without a real Bedrock call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository

API = "/api/v1"


def _patch_intent(monkeypatch, intent: dict):
    """Patch the classifier where the viewmodel imports it."""
    import app.viewmodels.chat_viewmodel as vm
    monkeypatch.setattr(vm, "classify_intent", AsyncMock(return_value=intent))


async def _proposal_in_phase(db, make_proposal_db, phase: str):
    agency, client, proposal = await make_proposal_db()
    repo = ProposalRepository(db)
    await repo.update(proposal.id, pipeline_state={"current_phase": phase})
    await db.commit()
    return agency, client, proposal


@pytest.mark.asyncio
async def test_re_run_phase_enqueues_job_and_acks(
    client, registered, arq_pool, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {"kind": "re_run_phase", "phase": "research", "confidence": 0.95})
    p = await make_proposal_api(client, registered.headers)
    # move out of brief
    await client.post(f"{API}/chat/{p['id']}/approve/brief", headers=registered.headers, json={"data": {}})

    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "redo the research"},
    )
    assert resp.status_code == 200
    # re_run_phase routes through enqueue_phase_job -> DEL + enqueue run_research
    arq_pool.delete.assert_awaited()
    assert arq_pool.delete.await_args.args[0] == f"arq:result:{p['id']}:run_research"
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"
    # an ack assistant message is returned/broadcast
    bodies = [m for m in resp.json()]
    assert any("research" in (m.get("content") or "").lower() for m in bodies)


@pytest.mark.asyncio
async def test_unknown_intent_returns_help(
    client, registered, arq_pool, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {"kind": "unknown", "confidence": 0.0})
    p = await make_proposal_api(client, registered.headers)
    await client.post(f"{API}/chat/{p['id']}/approve/brief", headers=registered.headers, json={"data": {}})

    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "asdfgh"},
    )
    assert resp.status_code == 200
    # no job enqueued for unknown
    arq_pool.enqueue_job.assert_not_awaited()
    text = " ".join((m.get("content") or "") for m in resp.json()).lower()
    assert "re-run" in text or "regenerate" in text or "can" in text  # help text


@pytest.mark.asyncio
async def test_edit_cost_item_updates_model_and_acks(
    client, registered, db, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {
        "kind": "edit_cost_item", "deliverable": "Logo",
        "field": "quantity", "value": 2, "confidence": 0.9,
    })
    p = await make_proposal_api(client, registered.headers)
    # seed a cost model + phase
    repo = ProposalRepository(db)
    await repo.update(
        p["id"],
        pipeline_state={"current_phase": "cost_model_review"},
        cost_model={"line_items": [
            {"deliverable": "Logo", "quantity": 1, "unit_cost": 100000, "total": 100000},
        ], "discount_amount": 0},
    )
    await db.commit()

    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "set Logo quantity to 2"},
    )
    assert resp.status_code == 200
    fresh = await repo.get_by_id(p["id"])
    assert fresh.cost_model["line_items"][0]["quantity"] == 2
    assert fresh.cost_model["line_items"][0]["total"] == 200000


@pytest.mark.asyncio
async def test_ask_question_answers_with_assistant_text(
    client, registered, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {
        "kind": "ask_question", "question": "what's my total?", "confidence": 0.8,
    })
    # The dispatcher's ask_question path makes a Sonnet call — mock it.
    import app.viewmodels.chat_viewmodel as vm
    monkeypatch.setattr(
        vm, "get_ai_service",
        lambda: AsyncMock(complete=AsyncMock(return_value=type("R", (), {"text": "Your total is ₹1,18,000."})())),
        raising=False,
    )
    p = await make_proposal_api(client, registered.headers)
    await client.post(f"{API}/chat/{p['id']}/approve/brief", headers=registered.headers, json={"data": {}})

    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "what's my total?"},
    )
    assert resp.status_code == 200
    text = " ".join((m.get("content") or "") for m in resp.json())
    assert "total" in text.lower()
```

NOTE on test realism: these tests assume `send_message` returns the user + ack messages as a JSON list (matching the current contract where it returns `[user_msg, assistant_msg]`). VERIFY the actual response serialization in `chat.py`'s send route and adjust assertions to match (it may wrap in an envelope). For `regenerate_section`/`refine_section`, add analogous tests that patch `regenerate_section_content` (from Task 2) with an AsyncMock and assert it was awaited with the right `section_type` — mirror the pattern above. Keep section-LLM work mocked.

### Step 2: Run tests — expect failures

Run: `cd backend && uv run pytest tests/integration/test_chat_intent_dispatch.py -v`
Expected: failures (dispatcher not wired; `classify_intent` not imported in viewmodel).

### Step 3: Implement the dispatcher

- [ ] In `backend/app/viewmodels/chat_viewmodel.py`, add top-of-file imports:
```python
from app.services.ai.chat_intent import PHASE_TO_JOB, classify_intent
from app.services.cost_model_service import CostItemEditError, apply_cost_item_edit, find_line_item_index
from app.services.sections.regeneration import regenerate_section_content
from app.services.llm import Tier, get_ai_service
```
(Use the module's existing import style — if it groups `from app.services...` together, slot these in there.)

- [ ] Replace the non-brief block in `send_message` (currently lines 134-138) with:
```python
        # Non-brief phases: classify the message and route to an action.
        await self._broadcast_typing(proposal_id, True)
        intent = await classify_intent(
            user_message=content,
            current_phase=current_phase,
            proposal_state_hint=self._intent_hint(proposal),
        )
        assistant_msg = await self._dispatch_intent(proposal, intent, current_phase)
        await self._broadcast_msg(proposal_id, assistant_msg)
        return [user_msg, assistant_msg]
```
If a `_broadcast_typing` helper doesn't exist, add a tiny one that broadcasts `{"type": "typing", "channel": "main", "is_typing": bool}` via `ws_manager.broadcast` — mirror the field names the frontend's `use-websocket.ts` `typing` handler expects (verify those field names: `channel` and the typing flag). If the brief path already sets typing via a helper, reuse it.

- [ ] Add `_intent_hint`:
```python
    def _intent_hint(self, proposal) -> dict:
        cost = proposal.cost_model or {}
        items = cost.get("line_items") or []
        return {
            "section_types": list(PHASE_TO_JOB.keys()) and self._available_sections(proposal),
            "cost_items": [str(i.get("deliverable", "")) for i in items if i.get("deliverable")],
        }
```
Simplify `_available_sections` to: return the 9 canonical section keys that currently exist on the proposal (or just the canonical list from `app.services.sections`). Keep it cheap — import `SECTION_ORDER` and return it; the hint is advisory.

- [ ] Add `_dispatch_intent`:
```python
    async def _dispatch_intent(self, proposal, intent, current_phase):
        kind = intent.get("kind", "unknown")
        proposal_id = proposal.id

        if kind == "re_run_phase":
            job = PHASE_TO_JOB[intent["phase"]]
            pipeline = self._set_job_queued(proposal, job)  # reuse existing helper
            await self.proposal_repo.update(proposal_id, pipeline_state=pipeline)
            await self._db.commit()
            await self._enqueue(job, proposal_id)  # DEL+enqueue via the shared helper
            return await self._make_ack(proposal_id, f"Re-running {intent['phase'].replace('_', ' ')}…", current_phase)

        if kind == "regenerate_section":
            await regenerate_section_content(
                proposal=proposal, section_type=intent["section_type"],
                refine_instructions=None, db=self._db,
            )
            return await self._make_ack(proposal_id, f"Regenerating {intent['section_type'].replace('_', ' ')}…", current_phase)

        if kind == "refine_section":
            await regenerate_section_content(
                proposal=proposal, section_type=intent["section_type"],
                refine_instructions=intent["instructions"], db=self._db,
            )
            return await self._make_ack(proposal_id, f"Refining {intent['section_type'].replace('_', ' ')} based on your input…", current_phase)

        if kind == "edit_cost_item":
            cost = proposal.cost_model or {}
            idx = find_line_item_index(cost, intent["deliverable"])
            if idx is None:
                return await self._make_ack(proposal_id, f"I couldn't find a cost item called \"{intent['deliverable']}\".", current_phase)
            try:
                updated = apply_cost_item_edit(cost, index=idx, field=intent["field"], value=intent["value"])
            except CostItemEditError:
                return await self._make_ack(proposal_id, "I couldn't apply that cost-model edit.", current_phase)
            await self.proposal_repo.update(proposal_id, cost_model=updated)
            await self._db.commit()
            await self._broadcast_cost_model(proposal_id, updated)  # if such a helper exists; else broadcast new_message only
            return await self._make_ack(proposal_id, f"Updated {intent['field'].replace('_', ' ')} for {intent['deliverable']}.", current_phase)

        if kind == "ask_question":
            answer = await self._answer_question(proposal, intent["question"])
            return await self._make_ack(proposal_id, answer, current_phase)

        # unknown
        return await self._echo_response(
            proposal_id, "", current_phase,
            override_text=(
                "I can re-run a phase (research, benchmarks, cost model, sections), "
                "regenerate or refine a section, edit a cost item, or answer questions "
                "about your proposal. Try: \"redo research\" or \"regenerate the problem statement\"."
            ),
        )
```

- [ ] Add `_make_ack` (create assistant text message; do NOT broadcast — the caller broadcasts the returned msg):
```python
    async def _make_ack(self, proposal_id, text, phase):
        return await self.msg_repo.create(
            proposal_id=proposal_id, role=MessageRole.ASSISTANT.value,
            message_type=MessageType.TEXT.value, content=text, phase=phase,
        )
```
Confirm the actual attribute names on the viewmodel (`self.msg_repo` vs `self._msg_repo`, `self.proposal_repo` vs `self._proposal_repo`, `self._db` vs `self._session`) by reading the existing methods in `chat_viewmodel.py` and matching them EXACTLY. The pseudocode uses placeholder names.

- [ ] Add `_answer_question` (single Sonnet turn with proposal context):
```python
    async def _answer_question(self, proposal, question) -> str:
        brief = proposal.brief or {}
        context = (
            f"Project: {proposal.project_name}\n"
            f"Brief: {brief}\n"
            f"Cost model: {proposal.cost_model or {}}\n"
        )
        result = await get_ai_service().complete(
            f"Answer the user's question about this proposal concisely.\n\n"
            f"{context}\n\nQuestion: {question}",
            tier=Tier.BALANCED,
            system="You are a helpful proposal assistant. Answer in 1-3 sentences using only the provided context.",
            max_tokens=400,
        )
        return result.text
```
Keep the context assembly pragmatic — don't dump giant section bodies; brief + cost_model + project name is enough for v1.

### Step 4: Run dispatch tests, then full suite

```
cd backend
uv run pytest tests/integration/test_chat_intent_dispatch.py -v
uv run pytest -q
```
Expected: dispatch tests pass; full suite green (prior count + all new tests).

### Step 5: ruff + commit

```bash
cd backend && uv run ruff check app/viewmodels/chat_viewmodel.py
git add backend/app/viewmodels/chat_viewmodel.py backend/tests/integration/test_chat_intent_dispatch.py
git commit -m "feat(chat): route non-brief messages through Path B intent dispatch"
```

---

## Sub-slice 2 done

- [ ] `git status` clean; `git branch --show-current` == `worktree-post-s10-stability-and-chat-intent`
- [ ] `cd backend && uv run pytest -q` fully green
- [ ] Frontend untouched (acks render as existing `text` bubbles); confirm `cd frontend && pnpm test --run` still 275 passing (should be unaffected, but verify since this is a slice boundary).

---

## Self-review checklist (pre-execution)

- [x] **Spec coverage:** all 6 intents (re_run_phase, regenerate_section, refine_section, edit_cost_item, ask_question, unknown) have a dispatch path + at least one test. Classifier is Haiku (Tier.FAST); ask_question answer is Sonnet (Tier.BALANCED). Out-of-scope items (multi-turn, new section types, brief edits, voice) are not added.
- [x] **Placeholder scan:** the only intentional "transcribe this" placeholders are in Task 2 (`_generate_section` body — must be read, can't be guessed) and Task 3 (`apply_cost_item_edit` arithmetic — must match the handler exactly). Both are explicitly flagged with why. The GST/grand_total test number is called out as "reconcile against the real handler formula."
- [x] **Type consistency:** `classify_intent(*, user_message, current_phase, proposal_state_hint)`, `Intent` kind set, and `PHASE_TO_JOB` keys ({research, benchmarks, cost_model, sections}) are consistent between Task 1 and Task 4. `regenerate_section_content(*, proposal, section_type, refine_instructions, db)` consistent between Task 2 and Task 4. `apply_cost_item_edit(cost_model, *, index, field, value)` + `find_line_item_index(cost_model, deliverable)` consistent between Task 3 and Task 4.
- [x] **Layering:** dispatcher calls only service-layer functions (no view-layer imports). Extractions (Tasks 2, 3) are pure refactors guarded by existing endpoint tests.
- [x] **Known verify-points flagged for implementers:** exact viewmodel attribute names (`self.msg_repo`/`self._db` etc.), the send-route response serialization shape, the `typing` WS field names, and the section-test double-monkeypatch target are all called out to be confirmed against real code rather than assumed.
```

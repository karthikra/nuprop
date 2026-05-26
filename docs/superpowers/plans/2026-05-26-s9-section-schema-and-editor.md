# S9 — Section Schema, Two-Pass Generation & Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the six-text-column proposal output with nine per-section JSON columns; replace the single `generate_narrative` LLM call with a two-pass generator (7 facts in parallel + 2 synthesis sequential); ship a long-form scrollable section editor with per-section edit / regenerate / refine / toggle-off. Text-only — media buttons land in S10 and S11.

**Architecture:** Each section type gets its own nullable JSON column on `proposals`, storing `{content, assets, included, metadata}`. The `SECTION_ORDER` constant in code drives canonical iteration; column-name to section-type is the identity. The new `generate_sections` ARQ phase replaces `generate_narrative` and `generate_outputs` — Pass 1 fans out 7 fact generators concurrently with `asyncio.gather`, Pass 2 runs the 2 synthesis generators sequentially using Pass 1 outputs. After `cost_model` approval the chat transitions the user into the new editor surface; the narrative approval gate is removed.

**Tech Stack:** Python 3.14 / SQLAlchemy async / Alembic / `AsyncAnthropicBedrock` via `AIService` (Sonnet 4.6, Tier.BALANCED) / FastAPI / ARQ / React 18 / TypeScript / React Query v5 / vitest + MSW.

**Spec:** `docs/superpowers/specs/2026-05-26-s9-s13-section-redesign-design.md`

**Working directory:** backend paths relative to `backend/`; frontend paths relative to `frontend/`. Both stacks are touched.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `backend/alembic/versions/05_proposal_section_columns.py` | Drop 7 old columns; add 9 new JSON section columns | Create |
| `backend/app/infrastructure/db/models/proposal.py` | Declare the 9 new columns; drop the 7 old ones | Modify |
| `backend/app/services/sections/__init__.py` | `SectionType` enum + `SECTION_ORDER`/`FACT_SECTIONS`/`SYNTHESIS_SECTIONS` constants + `default_sections_for_template` | Create |
| `backend/app/services/ai/section_facts.py` | 7 fact prompt builders + the shared `generate_fact_section` helper | Create |
| `backend/app/services/ai/section_synthesis.py` | 2 synthesis prompt builders + `generate_synthesis_section` helper | Create |
| `backend/app/services/pipeline_service.py` | Replace `generate_narrative` + `generate_outputs` with `generate_sections` orchestration | Modify |
| `backend/app/workers/pipeline.py` | Rename phases + update `_NEXT_PHASE` map | Modify |
| `backend/app/viewmodels/chat_viewmodel.py` | Remove the `narrative` gate entry from `gate_map`; route `cost_model` approval directly to `generate_sections` and emit a `section_editor` phase change | Modify |
| `backend/app/views/v1/proposals.py` | New section CRUD endpoints (`PATCH`, `regenerate`, `refine`) | Modify |
| `backend/app/domain/schemas/proposal_schemas.py` | Drop the 7 old fields from `ProposalResponse`; add the 9 new section fields | Modify |
| `backend/app/infrastructure/db/models/template.py` | Allow `config.default_sections: list[str]` (no model change — `config` is already JSON) | None (JSON-only) |
| `frontend/src/types/proposal.ts` | `Section` type + per-section fields on `Proposal` | Modify |
| `frontend/src/api/proposals.ts` | New hooks: `usePatchSection`, `useRegenerateSection`, `useRefineSection` | Modify |
| `frontend/src/components/sections/section-block.tsx` | The per-section editor block | Create |
| `frontend/src/components/sections/section-toolbar.tsx` | Edit / regenerate / refine / toggle-off toolbar | Create |
| `frontend/src/components/sections/section-editor.tsx` | The long-form scrollable container | Create |
| `frontend/src/components/chat/chat-container.tsx` | Transition into section-editor after `cost_model` approval; remove narrative-preview rendering | Modify |
| `frontend/src/components/chat/narrative-preview.tsx` | Delete the now-dead chat card | Delete |
| `docs/superpowers/HANDOFF.md` | Mark S9 complete | Modify |

---

### Task 1: Schema migration — 9 section columns

**Files:**
- Create: `backend/alembic/versions/05_proposal_section_columns.py`
- Modify: `backend/app/infrastructure/db/models/proposal.py`

- [ ] **Step 1: Modify the `Proposal` SQLAlchemy model**

In `backend/app/infrastructure/db/models/proposal.py`, **remove** the seven existing column declarations:

```python
    covering_letter: Mapped[str | None] = mapped_column(Text)
    covering_letter_alt: Mapped[str | None] = mapped_column(Text)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    scope_sections: Mapped[dict] = mapped_column(JSONColumn, default=list)
    cost_rationale: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)
    email_draft: Mapped[str | None] = mapped_column(Text)
```

**Add** the nine new section columns (place them after `pipeline_state` to keep S8's columns visually grouped):

```python
    # Section columns — each carries the full {content, assets, included, metadata}
    # payload; NULL means "section not yet generated"; included=false means
    # the user toggled it off. Canonical order lives in
    # app/services/sections/__init__.py::SECTION_ORDER.
    cover_page:           Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    executive_summary:    Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    problem_statement:    Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    proposed_solution:    Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    scope_of_work:        Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    timeline:             Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    pricing:              Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    qualifications:       Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    terms_and_conditions: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
```

- [ ] **Step 2: Create the Alembic migration**

Create `backend/alembic/versions/05_proposal_section_columns.py`:

```python
"""drop legacy text columns; add nine per-section JSON columns

Revision ID: 05_proposal_section_columns
Revises: 04_proposal_rate_card_columns
Create Date: 2026-05-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "05_proposal_section_columns"
down_revision = "04_proposal_rate_card_columns"
branch_labels = None
depends_on = None


_LEGACY_COLUMNS = [
    "covering_letter",
    "covering_letter_alt",
    "executive_summary",  # re-added below as JSON
    "scope_sections",
    "cost_rationale",
    "terms",
    "email_draft",
]

_SECTION_COLUMNS = [
    "cover_page",
    "executive_summary",
    "problem_statement",
    "proposed_solution",
    "scope_of_work",
    "timeline",
    "pricing",
    "qualifications",
    "terms_and_conditions",
]


def upgrade() -> None:
    for col in _LEGACY_COLUMNS:
        op.drop_column("proposals", col)
    for col in _SECTION_COLUMNS:
        op.add_column("proposals", sa.Column(col, sa.JSON(), nullable=True))


def downgrade() -> None:
    for col in reversed(_SECTION_COLUMNS):
        op.drop_column("proposals", col)
    # Recreate the legacy columns in their original types.
    op.add_column("proposals", sa.Column("covering_letter", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("covering_letter_alt", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("executive_summary", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("scope_sections", sa.JSON(), nullable=True))
    op.add_column("proposals", sa.Column("cost_rationale", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("terms", sa.Text(), nullable=True))
    op.add_column("proposals", sa.Column("email_draft", sa.Text(), nullable=True))
```

- [ ] **Step 3: Confirm alembic head**

Run: `.venv/bin/python -m alembic heads`
Expected: `05_proposal_section_columns (head)`. Single head.

- [ ] **Step 4: Run the suite — expect failures from the dropped columns**

Run: `.venv/bin/python -m pytest -q 2>&1 | tail -20`
Expected: FAIL. The model change drops columns that existing code reads (`pipeline_service.py:483`, etc.). Tests that touch `covering_letter` / `executive_summary` / `scope_sections` / `cost_rationale` / `terms` / `email_draft` will fail at collection or runtime. This is the expected red state — subsequent tasks land the matching code changes that bring the suite green.

Do NOT proceed to commit on this step alone — the schema migration is committed together with Task 2 (section helpers + the chat-and-pipeline migration of generate_narrative happens across Tasks 5-6). To keep this task self-contained, **delay the commit until Step 5 below.**

- [ ] **Step 5: Commit the schema change**

```bash
git add backend/app/infrastructure/db/models/proposal.py backend/alembic/versions/05_proposal_section_columns.py
git commit -m "feat(S9): replace 7 legacy text columns with 9 per-section JSON columns"
```

The suite will be RED at this commit — that's expected. Subsequent tasks land the matching code changes. The plan as a whole goes green at Task 12.

---

### Task 2: Section helpers — types, constants, defaults

**Files:**
- Create: `backend/app/services/sections/__init__.py`
- Create: `backend/tests/unit/test_section_helpers.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_section_helpers.py`:

```python
from __future__ import annotations

from app.services.sections import (
    FACT_SECTIONS,
    SECTION_ORDER,
    SYNTHESIS_SECTIONS,
    SectionType,
    default_sections_for_template,
    empty_section,
)


def test_section_order_has_nine_entries_in_canonical_sequence():
    assert SECTION_ORDER == [
        "cover_page",
        "executive_summary",
        "problem_statement",
        "proposed_solution",
        "scope_of_work",
        "timeline",
        "pricing",
        "qualifications",
        "terms_and_conditions",
    ]


def test_fact_and_synthesis_partition_covers_all_sections_disjointly():
    assert set(FACT_SECTIONS) | set(SYNTHESIS_SECTIONS) == set(SECTION_ORDER)
    assert not (set(FACT_SECTIONS) & set(SYNTHESIS_SECTIONS))
    assert len(FACT_SECTIONS) == 7
    assert len(SYNTHESIS_SECTIONS) == 2


def test_section_type_enum_values_match_section_order():
    assert {s.value for s in SectionType} == set(SECTION_ORDER)


def test_empty_section_returns_default_payload_shape():
    s = empty_section()
    assert s == {"content": "", "assets": [], "included": True, "metadata": {}}
    # Each call returns a fresh dict (no shared mutable state).
    s["assets"].append("contaminated")
    assert empty_section()["assets"] == []


def test_default_sections_for_template_returns_all_nine_when_no_template():
    assert default_sections_for_template(None) == set(SECTION_ORDER)


def test_default_sections_for_template_returns_all_nine_when_template_lacks_default_sections():
    assert default_sections_for_template({"narrative": {}}) == set(SECTION_ORDER)


def test_default_sections_for_template_returns_specified_subset_from_template_config():
    cfg = {"default_sections": ["problem_statement", "pricing", "executive_summary"]}
    assert default_sections_for_template(cfg) == {"problem_statement", "pricing", "executive_summary"}


def test_default_sections_for_template_ignores_unknown_section_names():
    cfg = {"default_sections": ["pricing", "not_a_real_section", "executive_summary"]}
    assert default_sections_for_template(cfg) == {"pricing", "executive_summary"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/unit/test_section_helpers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.sections'`.

- [ ] **Step 3: Write the helpers module**

Create `backend/app/services/sections/__init__.py`:

```python
"""Section types, canonical order, and template-defaults helper.

A NUPROP proposal is composed of nine canonical sections, persisted as nine
nullable JSON columns on the ``Proposal`` model. Each column carries the
``{content, assets, included, metadata}`` payload shape; ``SECTION_ORDER``
is the only reader/writer of canonical iteration sequence.
"""
from __future__ import annotations

import enum


class SectionType(str, enum.Enum):
    COVER_PAGE           = "cover_page"
    EXECUTIVE_SUMMARY    = "executive_summary"
    PROBLEM_STATEMENT    = "problem_statement"
    PROPOSED_SOLUTION    = "proposed_solution"
    SCOPE_OF_WORK        = "scope_of_work"
    TIMELINE             = "timeline"
    PRICING              = "pricing"
    QUALIFICATIONS       = "qualifications"
    TERMS_AND_CONDITIONS = "terms_and_conditions"


# Canonical render/iteration order. Frontend, generator, and export all read this.
SECTION_ORDER: list[str] = [
    SectionType.COVER_PAGE.value,
    SectionType.EXECUTIVE_SUMMARY.value,
    SectionType.PROBLEM_STATEMENT.value,
    SectionType.PROPOSED_SOLUTION.value,
    SectionType.SCOPE_OF_WORK.value,
    SectionType.TIMELINE.value,
    SectionType.PRICING.value,
    SectionType.QUALIFICATIONS.value,
    SectionType.TERMS_AND_CONDITIONS.value,
]

# Pass-1 (parallel) sections — generated from inputs independent of each other.
FACT_SECTIONS: list[str] = [
    SectionType.PROBLEM_STATEMENT.value,
    SectionType.PROPOSED_SOLUTION.value,
    SectionType.SCOPE_OF_WORK.value,
    SectionType.TIMELINE.value,
    SectionType.PRICING.value,
    SectionType.QUALIFICATIONS.value,
    SectionType.TERMS_AND_CONDITIONS.value,
]

# Pass-2 (sequential) sections — depend on the Pass-1 outputs.
SYNTHESIS_SECTIONS: list[str] = [
    SectionType.EXECUTIVE_SUMMARY.value,
    SectionType.COVER_PAGE.value,
]


def empty_section() -> dict:
    """The neutral payload for a section that exists but has no content yet."""
    return {"content": "", "assets": [], "included": True, "metadata": {}}


def default_sections_for_template(template_config: dict | None) -> set[str]:
    """Which section types are 'on by default' for this template.

    Templates may declare ``config.default_sections: list[str]``; otherwise all
    nine sections are included. Unknown section names in the template config
    are silently dropped.
    """
    if not template_config or "default_sections" not in template_config:
        return set(SECTION_ORDER)
    declared = template_config.get("default_sections") or []
    return {s for s in declared if s in SECTION_ORDER}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/unit/test_section_helpers.py -q`
Expected: PASS — 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sections/__init__.py backend/tests/unit/test_section_helpers.py
git commit -m "feat(S9): section types, canonical order, and template defaults"
```

---

### Task 3: Pass-1 fact-section generators

**Files:**
- Create: `backend/app/services/ai/section_facts.py`
- Create: `backend/tests/unit/test_section_facts.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_section_facts.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

import app.services.ai.section_facts as sf
from app.services.ai.section_facts import (
    PROMPT_BUILDERS,
    generate_fact_section,
)
from app.services.sections import FACT_SECTIONS


@pytest.fixture
def _fake_ai(monkeypatch):
    fake = AsyncMock()
    fake.complete = AsyncMock()
    fake.complete.return_value = AsyncMock(text="Generated section content.")
    monkeypatch.setattr(sf, "get_ai_service", lambda: fake)
    return fake


@pytest.mark.parametrize("section_type", FACT_SECTIONS)
def test_every_fact_section_has_a_registered_prompt_builder(section_type):
    assert section_type in PROMPT_BUILDERS


@pytest.mark.asyncio
async def test_generate_fact_section_returns_section_payload_shape(_fake_ai):
    payload = await generate_fact_section(
        section_type="problem_statement",
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        research=None,
        cost_model=None,
        template_config=None,
        context_brief=None,
        agency_name="Studio X",
    )
    assert set(payload.keys()) == {"content", "assets", "included", "metadata"}
    assert payload["content"] == "Generated section content."
    assert payload["assets"] == []
    assert payload["included"] is True
    assert isinstance(payload["metadata"], dict)


@pytest.mark.asyncio
async def test_generate_fact_section_invokes_llm_with_balanced_tier(_fake_ai):
    await generate_fact_section(
        section_type="pricing",
        brief={"client": {"name": "Acme"}},
        research=None,
        cost_model={"total": 500000, "line_items": []},
        template_config=None,
        context_brief=None,
        agency_name="Studio X",
    )
    _, kwargs = _fake_ai.complete.call_args
    assert kwargs["max_tokens"] == 2000
    # tier is passed as Tier.BALANCED enum
    from app.services.llm import Tier
    assert kwargs["tier"] == Tier.BALANCED


@pytest.mark.asyncio
async def test_generate_fact_section_raises_on_unknown_section_type():
    with pytest.raises(KeyError):
        await generate_fact_section(
            section_type="not_a_real_section",
            brief={},
            research=None,
            cost_model=None,
            template_config=None,
            context_brief=None,
            agency_name="Studio X",
        )


@pytest.mark.asyncio
async def test_pricing_metadata_carries_cost_model_total(_fake_ai):
    payload = await generate_fact_section(
        section_type="pricing",
        brief={"client": {"name": "Acme"}},
        research=None,
        cost_model={"total": 1_500_000, "line_items": [{"name": "Strategy", "amount": 1_500_000}]},
        template_config=None,
        context_brief=None,
        agency_name="Studio X",
    )
    assert payload["metadata"]["total"] == 1_500_000
    assert payload["metadata"]["line_item_count"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/unit/test_section_facts.py -q`
Expected: FAIL — module not present yet.

- [ ] **Step 3: Implement the fact generators**

Create `backend/app/services/ai/section_facts.py`:

```python
"""Pass-1 fact-section generators.

Each fact section is generated by a single LLM call that is independent of the
other fact sections (so the seven calls fan out concurrently). The shared
``generate_fact_section`` function dispatches to a per-type ``PromptBuilder`` —
one class per fact section — which owns its system prompt, user-prompt
construction, and optional metadata-extraction logic.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable

from app.services.llm import Tier, get_ai_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptBuilder:
    system: str
    user_template: Callable[..., str]
    metadata_fn: Callable[[str, dict], dict] | None = None


def _build_inputs_block(
    brief: dict,
    research: str | None,
    cost_model: dict | None,
    context_brief: str | None,
    agency_name: str,
) -> str:
    """Compact JSON block of inputs available to every fact section's prompt."""
    payload = {
        "agency_name": agency_name,
        "brief": brief or {},
    }
    if research:
        payload["research_summary"] = research[:8000]
    if cost_model:
        payload["cost_model"] = {
            "total": cost_model.get("total"),
            "line_items": cost_model.get("line_items", []),
            "tiered": cost_model.get("tiered", {}),
            "multipliers_applied": cost_model.get("multipliers_applied", []),
        }
    if context_brief:
        payload["client_context"] = context_brief[:4000]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _user_for_problem_statement(brief, research, cost_model, context_brief, agency_name) -> str:
    inputs = _build_inputs_block(brief, research, cost_model, context_brief, agency_name)
    return (
        "Inputs:\n```json\n" + inputs + "\n```\n\n"
        "Write the PROBLEM STATEMENT / NEEDS ASSESSMENT section of a proposal."
        " 2-4 short paragraphs in markdown. Demonstrate you understand the client's"
        " situation, pain point, or opportunity. Use details from the brief and"
        " client_context. Do not pitch the solution here; do not talk about the"
        " agency. Be specific to this client, not generic."
    )


def _user_for_proposed_solution(brief, research, cost_model, context_brief, agency_name) -> str:
    inputs = _build_inputs_block(brief, research, cost_model, context_brief, agency_name)
    return (
        "Inputs:\n```json\n" + inputs + "\n```\n\n"
        "Write the PROPOSED SOLUTION / APPROACH section. 3-5 paragraphs in markdown."
        " What you'll actually do, how, and why this approach. If natural, break into"
        " sub-headings for phases, methodology, or workstreams. Reference the brief's"
        " deliverables. Avoid generic language; be specific to this engagement."
    )


def _user_for_scope_of_work(brief, research, cost_model, context_brief, agency_name) -> str:
    inputs = _build_inputs_block(brief, research, cost_model, context_brief, agency_name)
    return (
        "Inputs:\n```json\n" + inputs + "\n```\n\n"
        "Write the SCOPE OF WORK / DELIVERABLES section. List the concrete outputs"
        " the client receives, as a markdown bulleted list grouped by category."
        " Where useful, also list explicit exclusions ('not included') to manage"
        " expectations. Use the brief's `project.deliverables` and the cost_model's"
        " `line_items` as the source of truth."
    )


def _user_for_timeline(brief, research, cost_model, context_brief, agency_name) -> str:
    inputs = _build_inputs_block(brief, research, cost_model, context_brief, agency_name)
    return (
        "Inputs:\n```json\n" + inputs + "\n```\n\n"
        "Write the TIMELINE / SCHEDULE section. Express as a markdown table with"
        " columns Phase | Duration | Milestone. Derive phases from the proposed"
        " solution / scope. If the brief specifies dates or a start window, anchor"
        " to them; otherwise express as relative durations (e.g. 'Week 1-3')."
    )


def _user_for_pricing(brief, research, cost_model, context_brief, agency_name) -> str:
    inputs = _build_inputs_block(brief, research, cost_model, context_brief, agency_name)
    return (
        "Inputs:\n```json\n" + inputs + "\n```\n\n"
        "Write the PRICING / BUDGET section. Lead with a one-paragraph summary of"
        " total cost and what's included, then a markdown table of line items"
        " (Item | Description | Cost in INR). If cost_model.tiered is non-empty,"
        " also describe each tier briefly. Conclude with payment structure if"
        " present in the brief. Be transparent about what's and isn't included."
    )


def _pricing_metadata(_text: str, cost_model: dict | None) -> dict:
    if not cost_model:
        return {}
    return {
        "total": cost_model.get("total"),
        "line_item_count": len(cost_model.get("line_items", [])),
        "tiered": bool(cost_model.get("tiered")),
    }


def _user_for_qualifications(brief, research, cost_model, context_brief, agency_name) -> str:
    inputs = _build_inputs_block(brief, research, cost_model, context_brief, agency_name)
    return (
        "Inputs:\n```json\n" + inputs + "\n```\n\n"
        "Write the QUALIFICATIONS / ABOUT US section for " + agency_name + "."
        " 2-3 short paragraphs in markdown. Cover: relevant experience for this"
        " kind of work, key team capabilities, and one or two specific past"
        " results if any can be inferred from the inputs. Avoid generic agency"
        " puffery — be concrete, specific, and short. If client_context mentions"
        " prior work with this client, lead with that."
    )


def _user_for_terms_and_conditions(brief, research, cost_model, context_brief, agency_name) -> str:
    inputs = _build_inputs_block(brief, research, cost_model, context_brief, agency_name)
    return (
        "Inputs:\n```json\n" + inputs + "\n```\n\n"
        "Write the TERMS AND CONDITIONS section. Markdown, concise. Cover:"
        " payment terms (use cost_model.tiered.payment_terms or a sensible default"
        " like '50% on signing, 50% on delivery'), validity period (30 days from"
        " issuance), IP ownership (deliverables transfer to client on full"
        " payment), revisions included (use cost_model.standard_revisions if"
        " present, default 2), and a short cancellation clause. Keep it readable"
        " — clients shouldn't need a lawyer to parse it."
    )


PROMPT_BUILDERS: dict[str, PromptBuilder] = {
    "problem_statement": PromptBuilder(
        system="You are a senior proposal writer for a creative agency. Write the requested section directly — no preamble, no meta-commentary, no 'Here is...' lead-in.",
        user_template=_user_for_problem_statement,
    ),
    "proposed_solution": PromptBuilder(
        system="You are a senior proposal writer. Write directly; no preamble.",
        user_template=_user_for_proposed_solution,
    ),
    "scope_of_work": PromptBuilder(
        system="You are a senior proposal writer. Write a markdown bulleted scope-of-work directly; no preamble.",
        user_template=_user_for_scope_of_work,
    ),
    "timeline": PromptBuilder(
        system="You are a senior proposal writer. Output a markdown table only; no preamble or trailing prose.",
        user_template=_user_for_timeline,
    ),
    "pricing": PromptBuilder(
        system="You are a senior proposal writer. Output the pricing section in markdown directly; no preamble.",
        user_template=_user_for_pricing,
        metadata_fn=_pricing_metadata,
    ),
    "qualifications": PromptBuilder(
        system="You are a senior proposal writer. Write directly; no preamble; no generic agency puffery.",
        user_template=_user_for_qualifications,
    ),
    "terms_and_conditions": PromptBuilder(
        system="You are a senior proposal writer. Write the T&C section in markdown directly; no preamble.",
        user_template=_user_for_terms_and_conditions,
    ),
}


async def generate_fact_section(
    section_type: str,
    brief: dict,
    research: str | None,
    cost_model: dict | None,
    template_config: dict | None,
    context_brief: str | None,
    agency_name: str,
) -> dict:
    """Generate one fact section and return its payload dict."""
    builder = PROMPT_BUILDERS[section_type]   # KeyError on unknown section
    user_prompt = builder.user_template(brief, research, cost_model, context_brief, agency_name)

    result = await get_ai_service().complete(
        prompt=user_prompt,
        system=builder.system,
        tier=Tier.BALANCED,
        max_tokens=2000,
    )

    metadata: dict = {}
    if builder.metadata_fn:
        metadata = builder.metadata_fn(result.text, cost_model or {})

    return {
        "content": result.text,
        "assets": [],
        "included": True,
        "metadata": metadata,
    }
```

The `template_config` parameter is accepted but not yet used per-section. The fact prompts already include the cost-model + brief; template-specific tone tuning is a future refinement.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/unit/test_section_facts.py -q`
Expected: PASS — 11 passed (5 parametric + 6 unique).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/section_facts.py backend/tests/unit/test_section_facts.py
git commit -m "feat(S9): seven fact-section prompt builders + shared generator"
```

---

### Task 4: Pass-2 synthesis-section generators

**Files:**
- Create: `backend/app/services/ai/section_synthesis.py`
- Create: `backend/tests/unit/test_section_synthesis.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_section_synthesis.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

import app.services.ai.section_synthesis as ss
from app.services.ai.section_synthesis import generate_synthesis_section


@pytest.fixture
def _fake_ai(monkeypatch):
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=AsyncMock(text="Synthesised content."))
    monkeypatch.setattr(ss, "get_ai_service", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_generate_executive_summary_consumes_pass1_sections(_fake_ai):
    pass1 = {
        "problem_statement": {"content": "Client has a brand recall issue."},
        "proposed_solution": {"content": "We propose a 6-month campaign."},
        "pricing":           {"content": "Total ~₹18L over six months."},
        "timeline":          {"content": "Phases over 6 months."},
    }
    payload = await generate_synthesis_section(
        section_type="executive_summary",
        brief={"client": {"name": "Acme"}, "project": {}},
        pass1_sections=pass1,
        context_brief=None,
        agency_name="Studio X",
    )
    assert set(payload.keys()) == {"content", "assets", "included", "metadata"}
    user_kwargs = _fake_ai.complete.call_args.kwargs
    # The Pass-1 sections must reach the prompt.
    assert "brand recall issue" in user_kwargs["prompt"]
    assert "6-month campaign" in user_kwargs["prompt"]


@pytest.mark.asyncio
async def test_generate_cover_page_returns_metadata_with_proposal_anchor_fields(_fake_ai):
    payload = await generate_synthesis_section(
        section_type="cover_page",
        brief={
            "client": {"name": "Acme"},
            "project": {"name": "Annual campaign"},
        },
        pass1_sections={"executive_summary": {"content": "Six-month campaign."}},
        context_brief=None,
        agency_name="Studio X",
    )
    assert payload["metadata"]["agency_name"] == "Studio X"
    assert payload["metadata"]["client_name"] == "Acme"
    assert payload["metadata"]["project_name"] == "Annual campaign"


@pytest.mark.asyncio
async def test_generate_synthesis_section_raises_on_unknown_type():
    with pytest.raises(KeyError):
        await generate_synthesis_section(
            section_type="not_a_synthesis_type",
            brief={},
            pass1_sections={},
            context_brief=None,
            agency_name="Studio X",
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/unit/test_section_synthesis.py -q`
Expected: FAIL — module not present.

- [ ] **Step 3: Implement the synthesis generators**

Create `backend/app/services/ai/section_synthesis.py`:

```python
"""Pass-2 synthesis-section generators.

The two synthesis sections — executive_summary and cover_page — read the
Pass-1 fact section outputs in addition to the brief. They run sequentially
after Pass 1 completes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.services.llm import Tier, get_ai_service

logger = logging.getLogger(__name__)


def _condense_pass1(pass1_sections: dict) -> str:
    """Compact serialisation of Pass-1 content for inclusion in synthesis prompts."""
    out: dict[str, str] = {}
    for key, payload in (pass1_sections or {}).items():
        content = (payload or {}).get("content")
        if content:
            out[key] = content[:3000]
    return json.dumps(out, ensure_ascii=False, indent=2)


async def _generate_executive_summary(
    brief: dict, pass1_sections: dict, context_brief: str | None, agency_name: str,
) -> dict:
    user_prompt = (
        "Pass-1 sections:\n```json\n" + _condense_pass1(pass1_sections) + "\n```\n\n"
        "Brief:\n```json\n" + json.dumps(brief or {}, ensure_ascii=False, indent=2) + "\n```\n\n"
        "Write the EXECUTIVE SUMMARY of this proposal. 1-2 short paragraphs in"
        " markdown. State the problem, your solution, and the key ask (cost and"
        " timeline) up front. This stands alone for decision-makers who read only"
        " this section. Do not invent details — use only what's in the inputs."
    )
    result = await get_ai_service().complete(
        prompt=user_prompt,
        system="You are a senior proposal writer. Write directly; no preamble.",
        tier=Tier.BALANCED,
        max_tokens=1500,
    )
    return {
        "content": result.text,
        "assets": [],
        "included": True,
        "metadata": {},
    }


async def _generate_cover_page(
    brief: dict, pass1_sections: dict, context_brief: str | None, agency_name: str,
) -> dict:
    project = (brief or {}).get("project") or {}
    client = (brief or {}).get("client") or {}
    project_name = project.get("name") or "Proposal"
    client_name = client.get("name") or "Client"

    exec_summary = ((pass1_sections or {}).get("executive_summary") or {}).get("content", "")

    user_prompt = (
        "Agency: " + agency_name + "\n"
        "Client: " + client_name + "\n"
        "Project: " + project_name + "\n\n"
        "Executive summary (first paragraph):\n" + exec_summary[:600] + "\n\n"
        "Write a SHORT cover-page body for a proposal. 1-2 sentences in markdown:"
        " an evocative one-line teaser that captures the engagement, plus the"
        " date. The agency name, client name, project name, and date are also"
        " sent separately as structured metadata — do not repeat them in the body."
    )
    result = await get_ai_service().complete(
        prompt=user_prompt,
        system="You are a senior proposal writer. Write a brief evocative cover-page teaser; no preamble.",
        tier=Tier.BALANCED,
        max_tokens=400,
    )

    return {
        "content": result.text,
        "assets": [],
        "included": True,
        "metadata": {
            "agency_name": agency_name,
            "client_name": client_name,
            "project_name": project_name,
            "issued_date": datetime.now(timezone.utc).date().isoformat(),
        },
    }


_SYNTHESIS_GENERATORS = {
    "executive_summary": _generate_executive_summary,
    "cover_page": _generate_cover_page,
}


async def generate_synthesis_section(
    section_type: str,
    brief: dict,
    pass1_sections: dict,
    context_brief: str | None,
    agency_name: str,
) -> dict:
    """Generate one synthesis section. Raises KeyError on unknown section_type."""
    return await _SYNTHESIS_GENERATORS[section_type](
        brief, pass1_sections, context_brief, agency_name,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/unit/test_section_synthesis.py -q`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/section_synthesis.py backend/tests/unit/test_section_synthesis.py
git commit -m "feat(S9): two synthesis-section generators reading Pass-1 outputs"
```

---

### Task 5: `generate_sections` pipeline phase + ARQ worker rename

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/app/workers/pipeline.py`
- Create: `backend/tests/integration/test_generate_sections.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_generate_sections.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.models.client import Client
from app.infrastructure.db.models.proposal import Proposal, ProposalStatus
from app.services.pipeline_service import PipelineService
from app.services.sections import FACT_SECTIONS, SYNTHESIS_SECTIONS


@pytest.fixture
async def _proposal_ready_for_sections(_schema, db):
    """Agency + client + proposal with brief committed and cost_model populated —
    the state immediately after the user approves the cost-model gate."""
    agency = Agency(name="Studio X", slug="studio-x")
    db.add(agency)
    await db.commit()
    client = Client(agency_id=agency.id, name="Acme", slug="acme", contacts=[])
    db.add(client)
    await db.commit()
    proposal = Proposal(
        agency_id=agency.id, client_id=client.id,
        project_name="Annual campaign",
        status=ProposalStatus.GENERATING.value,
        brief={
            "client": {"name": "Acme"},
            "project": {"name": "Annual campaign", "deliverables": [
                {"category": "strategy", "name": "Brand strategy"},
            ]},
        },
        cost_model={"total": 1500000, "line_items": [
            {"name": "Strategy", "amount": 1500000},
        ]},
        research="Brief research summary.",
        benchmarks="Market benchmark summary.",
    )
    db.add(proposal)
    await db.commit()
    return agency, proposal


@pytest.mark.asyncio
async def test_generate_sections_populates_all_seven_fact_columns(
    _proposal_ready_for_sections, db, monkeypatch,
):
    """After Pass 1 runs, all seven fact columns are populated with section payloads."""
    agency, proposal = _proposal_ready_for_sections

    # Stub both fact + synthesis generators so no real Bedrock calls occur.
    from app.services.ai import section_facts, section_synthesis

    async def _fake_fact(section_type, **_):
        return {"content": f"FACT {section_type}", "assets": [], "included": True, "metadata": {}}

    async def _fake_synth(section_type, **_):
        return {"content": f"SYNTH {section_type}", "assets": [], "included": True, "metadata": {}}

    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)
    monkeypatch.setattr(section_synthesis, "generate_synthesis_section", _fake_synth)

    svc = PipelineService(db, redis=AsyncMock())
    await svc.generate_sections(proposal.id)

    await db.refresh(proposal)
    for section_type in FACT_SECTIONS:
        column_value = getattr(proposal, section_type)
        assert column_value is not None, f"{section_type} should be populated"
        assert column_value["content"] == f"FACT {section_type}"
    for section_type in SYNTHESIS_SECTIONS:
        column_value = getattr(proposal, section_type)
        assert column_value is not None, f"{section_type} should be populated"
        assert column_value["content"] == f"SYNTH {section_type}"


@pytest.mark.asyncio
async def test_generate_sections_skips_sections_not_in_template_defaults(
    _proposal_ready_for_sections, db, monkeypatch,
):
    """When the proposal's template config lists default_sections, only those are generated."""
    agency, proposal = _proposal_ready_for_sections

    # Attach a template with limited default_sections to the proposal
    proposal.template_id = "minimal-template"
    await db.commit()

    # Stub PipelineService._load_template_config to return our test template.
    async def _fake_template_config(_self, _proposal):
        return {"default_sections": ["problem_statement", "pricing", "executive_summary"]}
    monkeypatch.setattr(PipelineService, "_load_template_config", _fake_template_config)

    from app.services.ai import section_facts, section_synthesis
    fact_calls: list[str] = []
    synth_calls: list[str] = []

    async def _fake_fact(section_type, **_):
        fact_calls.append(section_type)
        return {"content": "x", "assets": [], "included": True, "metadata": {}}

    async def _fake_synth(section_type, **_):
        synth_calls.append(section_type)
        return {"content": "x", "assets": [], "included": True, "metadata": {}}

    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)
    monkeypatch.setattr(section_synthesis, "generate_synthesis_section", _fake_synth)

    svc = PipelineService(db, redis=AsyncMock())
    await svc.generate_sections(proposal.id)

    assert set(fact_calls) == {"problem_statement", "pricing"}
    assert set(synth_calls) == {"executive_summary"}

    await db.refresh(proposal)
    assert proposal.problem_statement is not None
    assert proposal.pricing is not None
    assert proposal.executive_summary is not None
    # Sections not in default_sections stay NULL.
    assert proposal.cover_page is None
    assert proposal.proposed_solution is None
    assert proposal.scope_of_work is None
    assert proposal.timeline is None
    assert proposal.qualifications is None
    assert proposal.terms_and_conditions is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_generate_sections.py -q`
Expected: FAIL — `AttributeError: 'PipelineService' object has no attribute 'generate_sections'`.

- [ ] **Step 3: Remove the existing `generate_narrative` method from `pipeline_service.py`**

The current `generate_narrative` method spans roughly lines 426–530 and writes to the now-dropped columns (`covering_letter`, `covering_letter_alt`, `executive_summary`, `scope_sections`, `cost_rationale`, `terms`). Delete that whole method.

Also delete the entire current `generate_outputs` method (~lines 532–650). It writes to dropped columns and renders Astro. Its replacement is deferred to S12 (publish + share token); S9 has no output-generation step.

- [ ] **Step 4: Add `generate_sections` to `PipelineService`**

In `backend/app/services/pipeline_service.py`, at the top alongside the other AI-service imports, add:

```python
from app.services.ai.section_facts import generate_fact_section
from app.services.ai.section_synthesis import generate_synthesis_section
from app.services.sections import (
    FACT_SECTIONS,
    SECTION_ORDER,
    SYNTHESIS_SECTIONS,
    default_sections_for_template,
)
```

Add the new method on `PipelineService` (replacing the deleted `generate_narrative`):

```python
    async def generate_sections(self, proposal_id: UUID | str) -> None:
        """Pass-1 facts (parallel) + Pass-2 synthesis (sequential). Writes each
        section's payload to its dedicated column on the proposal."""
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            logger.warning("generate_sections: proposal %s not found", proposal_id)
            return

        agency_row = await self.session.execute(
            select(Agency).where(Agency.id == proposal.agency_id)
        )
        agency = agency_row.scalar_one()
        agency_name = agency.name

        template_config = await self._load_template_config(proposal)
        context_brief = await self._load_context_brief(proposal)
        default_sections = default_sections_for_template(template_config)

        # ── Pass 1 — fact sections in parallel ────────────────────────────────
        import asyncio
        fact_targets = [s for s in FACT_SECTIONS if s in default_sections]

        async def _one_fact(section_type: str) -> tuple[str, dict]:
            payload = await generate_fact_section(
                section_type=section_type,
                brief=proposal.brief or {},
                research=proposal.research,
                cost_model=proposal.cost_model or {},
                template_config=template_config,
                context_brief=context_brief,
                agency_name=agency_name,
            )
            return section_type, payload

        await self._emit_progress(proposal_id, "sections", "running", f"generating {len(fact_targets)} fact sections in parallel")
        fact_results = await asyncio.gather(*[_one_fact(s) for s in fact_targets])
        pass1_sections: dict[str, dict] = dict(fact_results)

        # Persist Pass-1 results before Pass-2 starts; one UPDATE per column.
        for section_type, payload in pass1_sections.items():
            await self.proposal_repo.update(proposal_id, **{section_type: payload})

        # ── Pass 2 — synthesis sections sequentially ──────────────────────────
        synth_targets = [s for s in SYNTHESIS_SECTIONS if s in default_sections]
        for section_type in synth_targets:
            await self._emit_progress(proposal_id, "sections", "running", f"synthesising {section_type}")
            payload = await generate_synthesis_section(
                section_type=section_type,
                brief=proposal.brief or {},
                pass1_sections=pass1_sections,
                context_brief=context_brief,
                agency_name=agency_name,
            )
            await self.proposal_repo.update(proposal_id, **{section_type: payload})

        await self.session.commit()

        # Phase transition: the new editor view takes over from here.
        pipeline = (proposal.pipeline_state or {}).copy()
        pipeline["current_phase"] = "section_editor"
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["sections"]
        await self.proposal_repo.update(proposal_id, pipeline_state=pipeline)
        await self.session.commit()

        await self._emit_phase_change(proposal_id, "section_editor")
```

`Agency` import: ensure `from app.infrastructure.db.models.agency import Agency` and `from sqlalchemy import select` are present at the top of the file (the file already uses `select` elsewhere).

- [ ] **Step 5: Update the ARQ worker phase chain**

In `backend/app/workers/pipeline.py`, find the `_NEXT_PHASE` dict (currently around line 26):

```python
_NEXT_PHASE = {
    "run_research": "run_benchmarks",
    "run_benchmarks": "build_cost_model",
}
```

Add the new `generate_sections` task. After `build_cost_model` is approved (which today goes through the cost_model approval gate before `generate_narrative` is enqueued), the gate now enqueues `generate_sections` directly. After `generate_sections` completes there is no next phase (the editor takes over) — so we don't add it to `_NEXT_PHASE`.

Find the existing task wrappers near the bottom of the file:

```python
async def generate_narrative(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "generate_narrative", proposal_id)


async def generate_outputs(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "generate_outputs", proposal_id)
```

Replace both with a single new task:

```python
async def generate_sections(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "generate_sections", proposal_id)
```

Then update `WorkerSettings.functions` (further down in the file) by removing `generate_narrative` and `generate_outputs` from the list and adding `generate_sections`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_generate_sections.py -q`
Expected: PASS — 2 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/app/workers/pipeline.py backend/tests/integration/test_generate_sections.py
git commit -m "feat(S9): generate_sections pipeline phase replaces narrative + outputs"
```

---

### Task 6: ChatViewModel gate change — `cost_model` approval enqueues `generate_sections`

**Files:**
- Modify: `backend/app/viewmodels/chat_viewmodel.py`
- Create: `backend/tests/integration/test_cost_model_gate_to_sections.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_cost_model_gate_to_sections.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.models.client import Client
from app.infrastructure.db.models.proposal import Proposal, ProposalStatus
from app.viewmodels.chat_viewmodel import ChatViewModel


@pytest.fixture
async def _proposal_at_cost_model_gate(_schema, db):
    agency = Agency(name="Studio X", slug="studio-x")
    db.add(agency)
    await db.commit()
    client = Client(agency_id=agency.id, name="Acme", slug="acme", contacts=[])
    db.add(client)
    await db.commit()
    proposal = Proposal(
        agency_id=agency.id, client_id=client.id,
        project_name="Annual campaign",
        status=ProposalStatus.GENERATING.value,
        brief={"client": {"name": "Acme"}},
        cost_model={"total": 1500000},
        pipeline_state={"current_phase": "cost_model_review", "phases_completed": []},
    )
    db.add(proposal)
    await db.commit()
    return agency, proposal


@pytest.mark.asyncio
async def test_approving_cost_model_gate_enqueues_generate_sections_not_narrative(
    _proposal_at_cost_model_gate, db, monkeypatch,
):
    """The narrative gate is gone. cost_model approval enqueues generate_sections directly."""
    agency, proposal = _proposal_at_cost_model_gate

    enqueued: list[str] = []

    async def _fake_enqueue(self, job_name, proposal_id):
        enqueued.append(job_name)

    monkeypatch.setattr(ChatViewModel, "_enqueue", _fake_enqueue)

    vm = ChatViewModel(request=MagicMock(), db=db, redis=AsyncMock())
    msg = await vm.approve_gate(proposal.id, agency.id, "cost_model", {})

    assert msg is not None
    assert enqueued == ["generate_sections"]


@pytest.mark.asyncio
async def test_narrative_gate_no_longer_exists(
    _proposal_at_cost_model_gate, db,
):
    """Approving a 'narrative' gate now returns a 400-style error (unknown gate)."""
    agency, proposal = _proposal_at_cost_model_gate

    vm = ChatViewModel(request=MagicMock(), db=db, redis=AsyncMock())
    result = await vm.approve_gate(proposal.id, agency.id, "narrative", {})

    assert result is None
    assert vm.error is not None
    assert "narrative" in vm.error.lower() or "unknown" in vm.error.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_cost_model_gate_to_sections.py -q`
Expected: FAIL — the current code's gate_map still has `narrative` and `cost_model → narrative` mapping.

- [ ] **Step 3: Update `gate_map` in `chat_viewmodel.py`**

In `backend/app/viewmodels/chat_viewmodel.py`, find `gate_map` (around line 265). Remove the `narrative` entry entirely and change `cost_model`'s target:

```python
        gate_map = {
            "template": (
                "research", "run_research",
                "Template confirmed. Starting client research and market benchmarking...",
            ),
            "cost_model": (
                "sections", "generate_sections",
                "Cost model approved. Drafting the proposal sections...",
            ),
        }
```

Find the existing `cost_model` branch lower down (around line 291). Today it sets `phases_completed = ... + ["cost_model_review"]` — leave that alone. Find the `narrative` branch (around line 293) which selects the alt covering letter — DELETE it; the covering-letter alt selection no longer exists in the section schema.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_cost_model_gate_to_sections.py -q`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/viewmodels/chat_viewmodel.py backend/tests/integration/test_cost_model_gate_to_sections.py
git commit -m "feat(S9): cost_model gate enqueues generate_sections; remove narrative gate"
```

---

### Task 7: Section CRUD endpoints — PATCH, regenerate, refine

**Files:**
- Modify: `backend/app/views/v1/proposals.py`
- Modify: `backend/app/domain/schemas/proposal_schemas.py`
- Create: `backend/tests/integration/test_section_endpoints.py`

- [ ] **Step 1: Update `ProposalResponse` schema**

In `backend/app/domain/schemas/proposal_schemas.py`, find `ProposalResponse`. Remove all references to the seven legacy fields (`covering_letter`, `covering_letter_alt`, `executive_summary` as Text, `scope_sections`, `cost_rationale`, `terms`, `email_draft`). Add the nine new section fields as `dict | None`:

```python
class ProposalResponse(BaseModel):
    # ...existing fields (id, agency_id, client_id, project_name, status,
    #   brief, template_id, preferences, research, benchmarks, context_brief,
    #   cost_model, rate_card_gaps, rate_card_override, pipeline_state, etc.) ...

    # The 9 section columns
    cover_page:           dict | None = None
    executive_summary:    dict | None = None
    problem_statement:    dict | None = None
    proposed_solution:    dict | None = None
    scope_of_work:        dict | None = None
    timeline:             dict | None = None
    pricing:              dict | None = None
    qualifications:       dict | None = None
    terms_and_conditions: dict | None = None

    model_config = ConfigDict(from_attributes=True)
```

(Adapt the `ConfigDict` line to match the existing style — Pydantic v2 in this repo.)

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/integration/test_section_endpoints.py`:

```python
from __future__ import annotations

import pytest


@pytest.fixture
async def _proposal_with_sections(client, _registered_agency_and_proposal_factory, db):
    """An agency + proposal whose problem_statement section is populated.
    The factory fixture is the standard 'create-an-agency-and-an-empty-proposal'
    helper in conftest.py."""
    agency, proposal, headers = await _registered_agency_and_proposal_factory()
    proposal.problem_statement = {
        "content": "Original content.",
        "assets": [],
        "included": True,
        "metadata": {},
    }
    await db.commit()
    return agency, proposal, headers


@pytest.mark.asyncio
async def test_patch_section_updates_content_and_returns_payload(
    _proposal_with_sections, client,
):
    agency, proposal, headers = _proposal_with_sections
    r = await client.patch(
        f"/api/v1/proposals/{proposal.id}/sections/problem_statement",
        headers=headers,
        json={"content": "Edited by user."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "Edited by user."
    assert body["included"] is True  # untouched


@pytest.mark.asyncio
async def test_patch_section_can_toggle_included_off(
    _proposal_with_sections, client,
):
    agency, proposal, headers = _proposal_with_sections
    r = await client.patch(
        f"/api/v1/proposals/{proposal.id}/sections/problem_statement",
        headers=headers,
        json={"included": False},
    )
    assert r.status_code == 200
    assert r.json()["included"] is False


@pytest.mark.asyncio
async def test_patch_unknown_section_type_returns_400(
    _proposal_with_sections, client,
):
    agency, proposal, headers = _proposal_with_sections
    r = await client.patch(
        f"/api/v1/proposals/{proposal.id}/sections/not_a_section",
        headers=headers,
        json={"content": "x"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_patch_section_404_when_proposal_belongs_to_other_agency(
    _proposal_with_sections, client,
):
    """An agency cannot patch another agency's proposal sections."""
    _, proposal, _ = _proposal_with_sections
    # Use a different (fake) auth header — should resolve to a different agency.
    other_headers = {"Authorization": "Bearer some-other-agency-token"}
    r = await client.patch(
        f"/api/v1/proposals/{proposal.id}/sections/problem_statement",
        headers=other_headers,
        json={"content": "intrusion"},
    )
    # Either 401 (no token resolved) or 404 (wrong agency) — both acceptable.
    assert r.status_code in (401, 404)


@pytest.mark.asyncio
async def test_regenerate_section_calls_the_fact_generator_and_writes_result(
    _proposal_with_sections, client, monkeypatch,
):
    agency, proposal, headers = _proposal_with_sections

    from app.services.ai import section_facts

    async def _fake_fact(section_type, **_):
        return {"content": f"REGENERATED {section_type}", "assets": [], "included": True, "metadata": {}}

    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)

    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/sections/problem_statement/regenerate",
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["content"] == "REGENERATED problem_statement"


@pytest.mark.asyncio
async def test_refine_section_passes_user_instructions_to_generator(
    _proposal_with_sections, client, monkeypatch,
):
    agency, proposal, headers = _proposal_with_sections

    from app.services.ai import section_facts
    captured_user_prompts: list[str] = []
    original = section_facts.generate_fact_section

    async def _capturing_generate(section_type, **kwargs):
        # Capture the user instruction via the kwargs (added by /refine).
        captured_user_prompts.append(kwargs.get("refine_instructions") or "")
        return {"content": "refined", "assets": [], "included": True, "metadata": {}}

    monkeypatch.setattr(section_facts, "generate_fact_section", _capturing_generate)

    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/sections/problem_statement/refine",
        headers=headers,
        json={"instructions": "Make it shorter and more formal."},
    )
    assert r.status_code == 200
    assert captured_user_prompts == ["Make it shorter and more formal."]
```

`_registered_agency_and_proposal_factory` is a conftest fixture you'll need to ensure exists. If it doesn't, copy the pattern from `tests/integration/test_rate_card_gaps_endpoints.py`'s setup helper.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_section_endpoints.py -q`
Expected: FAIL — endpoints don't exist.

- [ ] **Step 4: Add a `refine_instructions` kwarg to `generate_fact_section`**

In `backend/app/services/ai/section_facts.py`, extend the function signature:

```python
async def generate_fact_section(
    section_type: str,
    brief: dict,
    research: str | None,
    cost_model: dict | None,
    template_config: dict | None,
    context_brief: str | None,
    agency_name: str,
    refine_instructions: str | None = None,
) -> dict:
    """Generate one fact section and return its payload dict."""
    builder = PROMPT_BUILDERS[section_type]
    user_prompt = builder.user_template(brief, research, cost_model, context_brief, agency_name)
    if refine_instructions:
        user_prompt += (
            "\n\nREFINEMENT INSTRUCTIONS (the user wants the section adjusted): "
            + refine_instructions
        )

    result = await get_ai_service().complete(
        prompt=user_prompt,
        system=builder.system,
        tier=Tier.BALANCED,
        max_tokens=2000,
    )

    metadata: dict = {}
    if builder.metadata_fn:
        metadata = builder.metadata_fn(result.text, cost_model or {})

    return {
        "content": result.text,
        "assets": [],
        "included": True,
        "metadata": metadata,
    }
```

Same treatment for `generate_synthesis_section` in `section_synthesis.py` — add `refine_instructions: str | None = None` and append to the user prompt if present.

- [ ] **Step 5: Add the three endpoints**

In `backend/app/views/v1/proposals.py`, alongside the existing per-proposal routes:

```python
from app.services.sections import SECTION_ORDER, FACT_SECTIONS, SYNTHESIS_SECTIONS


class PatchSectionBody(BaseModel):
    content: str | None = None
    included: bool | None = None
    metadata: dict | None = None


class RefineSectionBody(BaseModel):
    instructions: str


def _validate_section_type(section_type: str) -> None:
    if section_type not in SECTION_ORDER:
        raise HTTPException(status_code=400, detail=f"Unknown section type: {section_type}")


@router.patch("/{proposal_id}/sections/{section_type}", status_code=200)
async def patch_section(
    proposal_id: UUID,
    section_type: str,
    body: PatchSectionBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    current = getattr(proposal, section_type) or {"content": "", "assets": [], "included": True, "metadata": {}}
    updated = {**current}
    if body.content is not None:
        updated["content"] = body.content
    if body.included is not None:
        updated["included"] = body.included
    if body.metadata is not None:
        updated["metadata"] = body.metadata

    await repo.update(proposal_id, **{section_type: updated})
    await db.commit()
    return updated


@router.post("/{proposal_id}/sections/{section_type}/regenerate", status_code=200)
async def regenerate_section(
    proposal_id: UUID,
    section_type: str,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    new_payload = await _generate_section(proposal, section_type, refine_instructions=None, db=db)
    await repo.update(proposal_id, **{section_type: new_payload})
    await db.commit()
    return new_payload


@router.post("/{proposal_id}/sections/{section_type}/refine", status_code=200)
async def refine_section(
    proposal_id: UUID,
    section_type: str,
    body: RefineSectionBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    new_payload = await _generate_section(
        proposal, section_type, refine_instructions=body.instructions, db=db,
    )
    await repo.update(proposal_id, **{section_type: new_payload})
    await db.commit()
    return new_payload


async def _generate_section(proposal, section_type: str, refine_instructions: str | None, db: AsyncSession) -> dict:
    """Dispatch a single fact-or-synthesis generation for one section. Used by
    /regenerate and /refine; shares no orchestration with the bulk pipeline phase."""
    from app.services.ai.section_facts import generate_fact_section
    from app.services.ai.section_synthesis import generate_synthesis_section
    from app.infrastructure.db.models.agency import Agency
    from sqlalchemy import select

    agency_row = await db.execute(select(Agency).where(Agency.id == proposal.agency_id))
    agency = agency_row.scalar_one()

    if section_type in FACT_SECTIONS:
        return await generate_fact_section(
            section_type=section_type,
            brief=proposal.brief or {},
            research=proposal.research,
            cost_model=proposal.cost_model or {},
            template_config=None,   # template-tuned prompts are deferred
            context_brief=proposal.context_brief,
            agency_name=agency.name,
            refine_instructions=refine_instructions,
        )

    # Synthesis section — must rebuild pass1_sections dict from the current proposal columns.
    pass1_sections = {s: getattr(proposal, s) or {} for s in FACT_SECTIONS}
    return await generate_synthesis_section(
        section_type=section_type,
        brief=proposal.brief or {},
        pass1_sections=pass1_sections,
        context_brief=proposal.context_brief,
        agency_name=agency.name,
        refine_instructions=refine_instructions,
    )
```

Note: `_generate_section` is a module-private helper, not a route. The synthesis generator passes `refine_instructions` similarly to the fact generator (handled in `section_synthesis.py` per Step 4).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_section_endpoints.py -q`
Expected: PASS — 6 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai/section_facts.py backend/app/services/ai/section_synthesis.py backend/app/views/v1/proposals.py backend/app/domain/schemas/proposal_schemas.py backend/tests/integration/test_section_endpoints.py
git commit -m "feat(S9): section CRUD endpoints — patch, regenerate, refine"
```

---

### Task 8: Frontend — section editor scaffold

**Files:**
- Modify: `frontend/src/types/proposal.ts`
- Modify: `frontend/src/api/proposals.ts`
- Create: `frontend/src/components/sections/section-editor.tsx`
- Modify: `frontend/src/pages/proposals/builder.tsx`

- [ ] **Step 1: Add the `Section` type and update `Proposal`**

In `frontend/src/types/proposal.ts`, add a `Section` interface and the per-section fields on `Proposal`:

```ts
export interface SectionAsset {
  id: string
  kind: 'image' | 'video' | 'audio'
  s3_key: string
  url: string
  caption: string | null
  ai_generated: boolean
  prompt?: string | null
  provider?: string | null
  width?: number | null
  height?: number | null
  duration_s?: number | null
  poster_s3_key?: string | null
}

export interface Section {
  content: string
  assets: SectionAsset[]
  included: boolean
  metadata: Record<string, unknown>
}

export const SECTION_ORDER: readonly string[] = [
  'cover_page',
  'executive_summary',
  'problem_statement',
  'proposed_solution',
  'scope_of_work',
  'timeline',
  'pricing',
  'qualifications',
  'terms_and_conditions',
] as const

export type SectionType = typeof SECTION_ORDER[number]

export const SECTION_TITLES: Record<SectionType, string> = {
  cover_page: 'Cover',
  executive_summary: 'Executive summary',
  problem_statement: 'Problem statement',
  proposed_solution: 'Proposed solution',
  scope_of_work: 'Scope of work',
  timeline: 'Timeline',
  pricing: 'Pricing',
  qualifications: 'Qualifications',
  terms_and_conditions: 'Terms & conditions',
}
```

Also remove from the `Proposal` interface the legacy fields (`covering_letter`, `executive_summary` if it was typed as string, `scope_sections`, etc.) and add per-section fields:

```ts
export interface Proposal {
  // ... existing fields ...
  cover_page: Section | null
  executive_summary: Section | null
  problem_statement: Section | null
  proposed_solution: Section | null
  scope_of_work: Section | null
  timeline: Section | null
  pricing: Section | null
  qualifications: Section | null
  terms_and_conditions: Section | null
}
```

- [ ] **Step 2: Add the section-API hooks**

In `frontend/src/api/proposals.ts`, append:

```ts
import type { Section, SectionType } from '../types/proposal'

export function usePatchSection(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      type: SectionType
      patch: { content?: string; included?: boolean; metadata?: Record<string, unknown> }
    }) => {
      const { data } = await api.patch<Section>(
        `/proposals/${proposalId}/sections/${vars.type}`,
        vars.patch,
      )
      return { type: vars.type, section: data }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useRegenerateSection(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (type: SectionType) => {
      const { data } = await api.post<Section>(
        `/proposals/${proposalId}/sections/${type}/regenerate`,
      )
      return { type, section: data }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useRefineSection(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { type: SectionType; instructions: string }) => {
      const { data } = await api.post<Section>(
        `/proposals/${proposalId}/sections/${vars.type}/refine`,
        { instructions: vars.instructions },
      )
      return { type: vars.type, section: data }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}
```

- [ ] **Step 3: Create the editor container**

Create `frontend/src/components/sections/section-editor.tsx`:

```tsx
import type { Proposal, SectionType } from '../../types/proposal'
import { SECTION_ORDER, SECTION_TITLES } from '../../types/proposal'
import { SectionBlock } from './section-block'

interface Props {
  proposal: Proposal
}

export function SectionEditor({ proposal }: Props) {
  // Render only sections that have been generated (non-null on the proposal).
  const items = SECTION_ORDER
    .map((type) => ({ type: type as SectionType, section: proposal[type as SectionType] }))
    .filter((item) => item.section !== null)

  if (items.length === 0) {
    return (
      <div className="text-sm text-stone-500 text-center py-12">
        Sections are being drafted… this takes about 30 seconds.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {items.map(({ type, section }) => (
        <SectionBlock
          key={type}
          proposalId={proposal.id}
          type={type}
          title={SECTION_TITLES[type]}
          section={section!}
        />
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Mount the editor in the builder page**

In `frontend/src/pages/proposals/builder.tsx`, the existing layout has the chat container on one side. Add the editor next to it (or below, depending on the current layout — match what's there). The editor renders when `proposal.pipeline_state?.current_phase === 'section_editor'`. Existing chat-cards continue to render before the section editor is reached. Insert into the right layout slot:

```tsx
import { SectionEditor } from '../../components/sections/section-editor'

// ... existing layout ...

{proposal.pipeline_state?.current_phase === 'section_editor' ? (
  <SectionEditor proposal={proposal} />
) : (
  // existing chat-only view stays for earlier phases
  <ChatContainer ... />
)}
```

Adapt the JSX structure to the existing builder page's layout shape. The key behavior is: when current_phase enters `section_editor`, the user sees the section list; before that, the chat is the primary surface.

- [ ] **Step 5: Run the suite (won't pass yet — `SectionBlock` isn't built until Task 9)**

Run: `pnpm test 2>&1 | tail -5`
Expected: type-error or import-error: `SectionBlock` is not defined yet.

This task ships the scaffold; Task 9 lands the missing block component and the suite goes green again.

- [ ] **Step 6: Commit (with the suite red — Task 9 brings it back to green)**

```bash
git add frontend/src/types/proposal.ts frontend/src/api/proposals.ts frontend/src/components/sections/section-editor.tsx frontend/src/pages/proposals/builder.tsx
git commit -m "feat(S9): section-editor scaffold + per-section API hooks"
```

---

### Task 9: Per-section block + toolbar

**Files:**
- Create: `frontend/src/components/sections/section-block.tsx`
- Create: `frontend/src/components/sections/section-toolbar.tsx`
- Create: `frontend/src/components/sections/__tests__/section-block.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/sections/__tests__/section-block.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { SectionBlock } from '../section-block'

const SAMPLE = {
  content: 'Original content.',
  assets: [],
  included: true,
  metadata: {},
}

describe('SectionBlock', () => {
  it('renders the section title and current content', () => {
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    expect(screen.getByText('Problem statement')).toBeInTheDocument()
    expect(screen.getByText('Original content.')).toBeInTheDocument()
  })

  it('auto-saves edited content after the debounce', async () => {
    const user = userEvent.setup()
    let lastBody: any = null
    server.use(
      http.patch(`${API}/proposals/p1/sections/problem_statement`, async ({ request }) => {
        lastBody = await request.json()
        return HttpResponse.json({ ...SAMPLE, content: lastBody.content })
      }),
    )
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    const editor = screen.getByRole('textbox', { name: /problem statement/i })
    await user.click(editor)
    await user.keyboard(' Added text.')
    await waitFor(
      () => expect(lastBody?.content).toMatch(/Added text\./),
      { timeout: 2000 },
    )
  })

  it('regenerate button posts to the regenerate endpoint and updates the block', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/proposals/p1/sections/problem_statement/regenerate`, () =>
        HttpResponse.json({ ...SAMPLE, content: 'Fresh content.' }),
      ),
    )
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    await user.click(screen.getByRole('button', { name: /regenerate/i }))
    await waitFor(() => expect(screen.getByText(/Fresh content\./i)).toBeInTheDocument())
  })

  it('refine flow opens a prompt field, submits the instructions, and replaces content', async () => {
    const user = userEvent.setup()
    let lastBody: any = null
    server.use(
      http.post(`${API}/proposals/p1/sections/problem_statement/refine`, async ({ request }) => {
        lastBody = await request.json()
        return HttpResponse.json({ ...SAMPLE, content: 'Shorter content.' })
      }),
    )
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    await user.click(screen.getByRole('button', { name: /refine/i }))
    const prompt = screen.getByLabelText(/refinement instructions/i)
    await user.type(prompt, 'Make it shorter')
    await user.click(screen.getByRole('button', { name: /apply refinement/i }))
    await waitFor(() => expect(lastBody).toEqual({ instructions: 'Make it shorter' }))
    await waitFor(() => expect(screen.getByText('Shorter content.')).toBeInTheDocument())
  })

  it('toggle-off greys out the block and shows a re-include action', async () => {
    const user = userEvent.setup()
    server.use(
      http.patch(`${API}/proposals/p1/sections/problem_statement`, async ({ request }) => {
        const body = await request.json() as { included?: boolean }
        return HttpResponse.json({ ...SAMPLE, included: body.included ?? true })
      }),
    )
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    await user.click(screen.getByRole('button', { name: /exclude this section/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /re-include/i })).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm test -- src/components/sections/__tests__/section-block.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Build the toolbar**

Create `frontend/src/components/sections/section-toolbar.tsx`:

```tsx
import { useState } from 'react'

interface Props {
  isRegenerating: boolean
  isRefining: boolean
  isIncluded: boolean
  onRegenerate: () => void
  onRefine: (instructions: string) => void
  onToggleInclude: () => void
}

export function SectionToolbar({
  isRegenerating, isRefining, isIncluded,
  onRegenerate, onRefine, onToggleInclude,
}: Props) {
  const [showRefineField, setShowRefineField] = useState(false)
  const [refineText, setRefineText] = useState('')

  const submitRefine = () => {
    const text = refineText.trim()
    if (!text) return
    onRefine(text)
    setShowRefineField(false)
    setRefineText('')
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs">
        <button
          onClick={onRegenerate}
          disabled={isRegenerating || isRefining}
          className="rounded-md border border-stone-200 px-2 py-1 hover:bg-stone-50 disabled:opacity-50"
        >
          {isRegenerating ? 'Regenerating…' : '↻ Regenerate'}
        </button>
        <button
          onClick={() => setShowRefineField(v => !v)}
          disabled={isRegenerating || isRefining}
          className="rounded-md border border-stone-200 px-2 py-1 hover:bg-stone-50 disabled:opacity-50"
        >
          💬 Refine
        </button>
        <button
          onClick={onToggleInclude}
          className="ml-auto rounded-md border border-stone-200 px-2 py-1 hover:bg-stone-50 text-stone-600"
        >
          {isIncluded ? 'Exclude this section' : 'Re-include'}
        </button>
      </div>

      {showRefineField ? (
        <div className="rounded-md border border-stone-200 bg-stone-50 p-2 space-y-2">
          <label className="text-xs text-stone-600 block" htmlFor="refine-instructions">
            Refinement instructions
          </label>
          <textarea
            id="refine-instructions"
            aria-label="Refinement instructions"
            value={refineText}
            onChange={(e) => setRefineText(e.target.value)}
            rows={2}
            placeholder="e.g. Make it shorter and more formal"
            className="w-full rounded-md border border-stone-300 px-2 py-1 text-xs"
          />
          <div className="flex gap-2">
            <button
              onClick={submitRefine}
              disabled={isRefining || !refineText.trim()}
              className="rounded-md bg-stone-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {isRefining ? 'Applying…' : 'Apply refinement'}
            </button>
            <button
              onClick={() => { setShowRefineField(false); setRefineText('') }}
              className="rounded-md border border-stone-300 px-3 py-1 text-xs"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 4: Build the section block**

Create `frontend/src/components/sections/section-block.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import type { Section, SectionType } from '../../types/proposal'
import {
  usePatchSection,
  useRegenerateSection,
  useRefineSection,
} from '../../api/proposals'
import { SectionToolbar } from './section-toolbar'

interface Props {
  proposalId: string
  type: SectionType
  title: string
  section: Section
}

export function SectionBlock({ proposalId, type, title, section }: Props) {
  const [draft, setDraft] = useState(section.content)
  const [included, setIncluded] = useState(section.included)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync local state when upstream section changes (e.g. after regenerate).
  useEffect(() => {
    setDraft(section.content)
    setIncluded(section.included)
  }, [section.content, section.included])

  const patch = usePatchSection(proposalId)
  const regenerate = useRegenerateSection(proposalId)
  const refine = useRefineSection(proposalId)

  const onChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value
    setDraft(next)
    if (debounceRef.current !== null) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      patch.mutate({ type, patch: { content: next } })
      debounceRef.current = null
    }, 1000)
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) clearTimeout(debounceRef.current)
    }
  }, [])

  const onRegenerate = () => regenerate.mutate(type)
  const onRefine = (instructions: string) => refine.mutate({ type, instructions })
  const onToggleInclude = () => {
    const next = !included
    setIncluded(next)
    patch.mutate({ type, patch: { included: next } })
  }

  return (
    <article className={`rounded-xl border border-stone-200 bg-white p-5 ${included ? '' : 'opacity-50'}`}>
      <header className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="text-base font-semibold text-stone-900">{title}</h2>
      </header>

      {included ? (
        <textarea
          aria-label={title}
          value={draft}
          onChange={onChange}
          rows={Math.max(4, draft.split('\n').length)}
          className="w-full rounded-md border border-stone-200 px-3 py-2 text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-stone-300"
        />
      ) : (
        <p className="text-sm text-stone-500 italic">Excluded from this proposal.</p>
      )}

      <div className="mt-3">
        <SectionToolbar
          isRegenerating={regenerate.isPending}
          isRefining={refine.isPending}
          isIncluded={included}
          onRegenerate={onRegenerate}
          onRefine={onRefine}
          onToggleInclude={onToggleInclude}
        />
      </div>
    </article>
  )
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pnpm test -- src/components/sections/__tests__/section-block.test.tsx`
Expected: PASS — 5 passed.

Then the full suite:

Run: `pnpm test 2>&1 | tail -5`
Expected: existing 260 tests + 5 new = 265 pass; the failures from Task 8 (missing SectionBlock) are now gone.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/sections/section-block.tsx frontend/src/components/sections/section-toolbar.tsx frontend/src/components/sections/__tests__/section-block.test.tsx
git commit -m "feat(S9): section block editor with auto-save, regenerate, refine, toggle"
```

---

### Task 10: Chat-container transition + remove narrative-preview

**Files:**
- Modify: `frontend/src/components/chat/chat-container.tsx`
- Delete: `frontend/src/components/chat/narrative-preview.tsx`

- [ ] **Step 1: Find usages of `narrative-preview.tsx`**

Run: `grep -rn "narrative-preview\|NarrativePreview" frontend/src/`

Expected: at minimum, an import + render in `chat-container.tsx`. There may also be a route or page reference.

- [ ] **Step 2: Remove the import and the rendering**

In `frontend/src/components/chat/chat-container.tsx`:
- Delete `import { NarrativePreview } from './narrative-preview'`.
- Delete the conditional render block that mounts `<NarrativePreview ... />` (typically gated on `current_phase === 'narrative_review'`).
- Where the chat used to render `<NarrativePreview />`, render nothing — the user transitions into the new section editor (mounted at the builder page level, per Task 8). The chat-container's role is now to render only the conversational chat up to the cost-model approval gate.

- [ ] **Step 3: Delete the file**

```bash
git rm frontend/src/components/chat/narrative-preview.tsx
```

- [ ] **Step 4: Run the suite**

Run: `pnpm test 2>&1 | tail -5`
Expected: 265 pass (no regression). If any test imports `narrative-preview`, delete or update that test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/chat-container.tsx
git commit -m "refactor(S9): remove narrative-preview chat card; section editor replaces it"
```

---

### Task 11: Update existing tests touching the dropped columns

**Files:**
- Modify: `backend/tests/integration/test_pipeline_service.py`
- Modify: `backend/tests/integration/test_s5_phase_context.py`
- Modify: `backend/tests/integration/test_ideation_service.py`
- Modify: `backend/tests/unit/test_ideation_prompt.py`
- Modify any other test that constructs a `Proposal(...)` with the dropped fields

- [ ] **Step 1: Find every test reference to the dropped columns**

Run: `grep -rln "covering_letter\|covering_letter_alt\|cost_rationale\|email_draft\|scope_sections" backend/tests/`

Expected: the four files above plus possibly others. Open each.

- [ ] **Step 2: Update each test**

For each test that constructs a `Proposal(...)` with the dropped fields, REMOVE those fields from the constructor call. They no longer exist on the model.

For each test that asserts on those fields (e.g. `assert proposal.covering_letter == "..."`), update the assertion:
- If the test is checking that `generate_narrative` produced output → either delete the test (the phase no longer exists) or rewrite to check the matching new section column (e.g. `proposal.executive_summary["content"]` for what was `proposal.executive_summary`).
- If the test is checking ideation output → the ideation phase doesn't write to those columns; the assertion is probably about `proposal.preferences` or chat messages, NOT about narrative fields. Inspect carefully.

For `test_s5_phase_context.py` — this tests that `_load_context_brief` is called in each pipeline phase. The `generate_narrative` phase no longer exists; replace that test with one that checks `generate_sections` calls `_load_context_brief`.

This step is repetitive; expect 20-40 line edits across 4 files.

- [ ] **Step 3: Run the full backend suite**

Run: `.venv/bin/python -m pytest -q`
Expected: the failures from Task 1's schema migration are gone. New count: 359 (S8 baseline) + ~25 new S9 tests + small adjustments = roughly **380 pass**, exit 0.

If anything still fails, address the failure inline and re-run.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test(S9): update legacy-column references in existing tests to new section schema"
```

---

### Task 12: Full regression + HANDOFF

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`

- [ ] **Step 1: Run the full backend suite from `backend/`**

Run: `.venv/bin/python -m pytest -q`
Expected: ~380 passing, exit 0.

- [ ] **Step 2: Run the full frontend suite from `frontend/`**

Run: `pnpm test`
Expected: ~265 passing, exit 0.

- [ ] **Step 3: Confirm migration head**

Run from `backend/`: `.venv/bin/python -m alembic heads`
Expected: single head `05_proposal_section_columns (head)`.

- [ ] **Step 4: Verify no legacy column references remain in app code**

Run from the repo root: `grep -rn "covering_letter\|covering_letter_alt\|cost_rationale\|email_draft\|scope_sections" backend/app/ frontend/src/`
Expected: zero matches. (Matches in `backend/tests/` or `backend/alembic/versions/` are fine — those are the test suite and the migration's `_LEGACY_COLUMNS` list.)

- [ ] **Step 5: Update `docs/superpowers/HANDOFF.md`**

Edit three places:

(a) Top "Last updated" block:
```
**Last updated:** 2026-05-XX (S9 section schema + editor shipped; pending merge)
**Latest commit on `main`:** `<post-S8>`. S9 lives on branch `worktree-s9-section-schema-and-editor` pending merge.
**Working tree:** clean inside the S9 worktree. `main` is still in sync with `origin/main`.
```
Look up the actual main HEAD via `git -C <repo-root> rev-parse --short main`.

(b) Roadmap status line: append the S9 line beneath the existing post-roadmap line.

```
**Post-roadmap slices:** S8 (smart rate card) COMPLETE. S9 (section schema + two-pass generation + editor) COMPLETE — see "What happened this session" below.
```

(c) Insert a new session section above the existing 2026-05-24 (S8) section:

```markdown
## What happened this session (2026-05-XX — S9)

Shipped **S9 — section schema + two-pass LLM generation + long-form editor**, the first slice of the S9-S13 section-redesign roadmap.

### Architecture

- **Schema:** 7 legacy text columns dropped, 9 new JSON columns added — one per canonical section type. Each column carries `{content, assets, included, metadata}`. Migration `05_proposal_section_columns`.
- **Two-pass generation:** `PipelineService.generate_sections` replaces `generate_narrative` and `generate_outputs`. Pass 1 runs 7 fact generators in parallel via `asyncio.gather`; Pass 2 runs 2 synthesis generators sequentially with Pass 1 outputs in the prompt. All section generators are in `app/services/ai/section_facts.py` and `section_synthesis.py`.
- **Approval flow:** the narrative gate is removed. Cost-model approval enqueues `generate_sections` directly. After generation completes, the pipeline transitions to a new `section_editor` phase and the frontend surfaces the editor.
- **Section CRUD:** `PATCH /proposals/{id}/sections/{type}` (content / included / metadata), `POST /sections/{type}/regenerate` (fresh LLM variant), `POST /sections/{type}/refine` (instruction-steered rewrite).
- **Frontend:** new `components/sections/section-editor.tsx` renders the included sections in canonical order. Each section is a `section-block.tsx` with auto-save (1s debounce), regenerate, refine-with-prompt, and toggle-off. No media yet (S10 unlocks images, S11 unlocks video + audio).

### Test counts

- Backend: ~359 → **~380** (+~21 across section helpers, fact / synthesis generators, the generate_sections phase, the section CRUD endpoints, and the cost-model-gate change).
- Frontend: 260 → **265** (+5 for the section-block component).
- Migration head: `05_proposal_section_columns`.

### Non-goals carried forward to S10–S13

- Media (image / video / audio): S10 + S11.
- NUSTAGE export + share token + Publish: S12.
- Context UX (persistent chip + Gmail picker): S13.
- CTA / Appendices section types: deferred entirely.
- DOCX / PDF: removed in S9; will return as downloadable artifacts in S12.
```

- [ ] **Step 6: Commit the doc**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(S9): mark S9 complete; section schema + editor shipped"
```

---

## Self-review notes

- **Spec coverage:** Piece A (schema) → Task 1; Piece B (two-pass generation) → Tasks 3-5; Piece C (editor) → Tasks 8-10; Piece F (context UX) → out of scope per the explicit S9 scope (lives in S13); template `default_sections` → Task 2 + used in Task 5.
- **Schema-shape consistency:** `Section = {content, assets, included, metadata}` is referenced identically across the model (Task 1), the helper (`empty_section()` in Task 2), the fact generator return (Task 3), the synthesis generator return (Task 4), the endpoints (Task 7), and the frontend `Section` interface (Task 8). Every reader and writer uses the same key set.
- **Canonical order:** `SECTION_ORDER` lives in one place (`app/services/sections/__init__.py`) and is re-declared on the frontend side as a `readonly string[]` (`types/proposal.ts`). The frontend matches the backend ordering by hand because the two stacks don't share types; the assertion in Task 2 Step 1 plus the readonly array in Task 8 guard against drift.
- **Phase chain:** the worker's `_NEXT_PHASE` map handles `run_research → run_benchmarks → build_cost_model` as today (S9 doesn't touch them). After `build_cost_model` the chat gate ("approve cost model") is the bridge — it enqueues `generate_sections` directly. After `generate_sections` there is no auto-next; the editor takes over.
- **Test red period:** the schema migration in Task 1 leaves the suite RED until Tasks 5-7 land the matching code, and Task 11 updates the legacy assertions. Implementers running this plan from scratch should expect the failing-suite state from Task 1's commit through Task 10's commit, going green at Task 11's commit. Subagent-driven execution naturally handles this by completing tasks in order.
- **Conftest fixture name (`_registered_agency_and_proposal_factory`):** referenced in Task 7's tests. If that exact fixture doesn't exist in `conftest.py`, the implementer must add it alongside the existing agency / proposal fixtures — copying the pattern from `test_rate_card_gaps_endpoints.py` from S8 is the easiest reference. The fixture's contract: return `(agency, proposal, headers)` for an authenticated POST/PATCH against the proposal.

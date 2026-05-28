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
# mapped to the ARQ job that runs it. Single source of truth for
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
- "re_run_phase": user wants to re-run a pipeline phase. Field `phase` in {research, benchmarks, cost_model, sections}.
- "regenerate_section": user wants a section regenerated from scratch. Field `section_type` (one of the available sections).
- "refine_section": user wants a section adjusted with guidance. Fields `section_type` and `instructions` (the user's guidance).
- "edit_cost_item": user wants to change a cost line item. Fields `deliverable` (the item name), `field` in {quantity, unit_cost}, `value` (integer).
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

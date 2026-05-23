"""LLM-driven rate-card gap analyser.

Given a brief, asks Claude to identify the hourly roles and offering categories
that the cost-model phase will need to price the proposal. Returns plain
``{needed_roles: [str], needed_offerings: [str]}``. The diff against the actual
rate card is the caller's job — this module is pure inference.
"""
from __future__ import annotations

import json
import logging

from app.services.llm import Tier, get_ai_service

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a costing assistant for a creative agency. Given a proposal brief,"
    " identify which hourly billing roles and which offering categories the"
    " agency's rate card would need to price this proposal."
    "\n\n"
    "Return STRICT JSON with two arrays of lowercase snake_case keys:"
    "\n"
    '  {"needed_roles": ["senior_strategist", "junior_designer"],'
    ' "needed_offerings": ["annual_retainer", "brand_identity"]}'
    "\n\n"
    "Keys must be lowercase snake_case identifiers an agency would naturally use in a rate card."
    " Do not invent specifics that aren't implied by the brief. Return empty arrays if unsure."
)


async def analyze_gaps(brief: dict) -> dict:
    """Return ``{"needed_roles": [...], "needed_offerings": [...]}`` for the brief.

    Failure-safe: on any LLM error or malformed response, returns empty lists.
    The cost-model fallback path is the safety net.
    """
    user_prompt = (
        "Brief:\n```json\n"
        + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n```\n\nReturn the JSON described above."
    )

    try:
        result = await get_ai_service().complete_json(
            prompt=user_prompt,
            system=_SYSTEM,
            tier=Tier.BALANCED,
            max_tokens=400,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "rate_gap_analyzer LLM call failed; treating as no gaps",
            extra={"event": "rate_gap.llm_failed", "error": str(exc)},
        )
        return {"needed_roles": [], "needed_offerings": []}

    if not isinstance(result, dict):
        return {"needed_roles": [], "needed_offerings": []}

    roles = result.get("needed_roles") or []
    offerings = result.get("needed_offerings") or []
    if not isinstance(roles, list):
        roles = []
    if not isinstance(offerings, list):
        offerings = []
    return {
        "needed_roles": [str(r) for r in roles if isinstance(r, (str, int))],
        "needed_offerings": [str(o) for o in offerings if isinstance(o, (str, int))],
    }

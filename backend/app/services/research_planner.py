"""Pre-flight plan generation for the run_research and run_benchmarks phases.

A short Haiku call before the slow web-search call begins. The plan is shown
to the user as a chat message so they know what to expect during the wait
and have an audit trail later.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.llm import Tier, get_ai_service

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

Given the brief and the list of deliverable categories, return:
  - "queries":   3-6 specific search queries you'd run for pricing data
                 (each a string — e.g. "logo design agency rates India
                 2024" not "design pricing")
  - "rationale": one short paragraph explaining what these queries
                 collectively will tell us about market rates and how
                 we'll use it.

Return ONLY valid JSON. No prose, no markdown fences."""


async def generate_research_plan(*, brief: dict) -> dict[str, Any]:
    """Produce a short structured plan for the upcoming research run.

    Returns a dict with ``queries`` (list[str]) and ``rationale`` (str).
    """
    ai = get_ai_service()
    return await ai.complete_json(
        prompt=json.dumps({"brief": brief}),
        tier=Tier.FAST,
        system=_RESEARCH_PLAN_SYSTEM,
        max_tokens=512,
    )


async def generate_benchmarks_plan(*, brief: dict) -> dict[str, Any]:
    """Produce a short structured plan for the upcoming benchmarks run.

    Returns a dict with ``queries`` (list[str]) and ``rationale`` (str).
    The brief's deliverable categories are surfaced in the prompt so the
    planner can suggest pricing-specific queries.
    """
    ai = get_ai_service()
    deliverables = (brief.get("project", {}) or {}).get("deliverables", []) or []
    return await ai.complete_json(
        prompt=json.dumps({"brief": brief, "deliverables": deliverables}),
        tier=Tier.FAST,
        system=_BENCHMARKS_PLAN_SYSTEM,
        max_tokens=512,
    )

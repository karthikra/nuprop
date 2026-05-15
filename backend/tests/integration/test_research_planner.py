"""Unit tests for the Haiku-based pre-flight plan generators."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.research_planner import generate_benchmarks_plan, generate_research_plan
from app.services.llm import Tier


class _StubAI:
    """Minimal AIService stand-in capturing the kwargs of complete_json."""

    def __init__(self, payload):
        self._payload = payload
        self.complete_json = AsyncMock(return_value=payload)


async def test_generate_research_plan_returns_queries_and_rationale(monkeypatch):
    ai = _StubAI({"queries": ["q1", "q2", "q3"], "rationale": "because reasons"})
    monkeypatch.setattr(
        "app.services.research_planner.get_ai_service", lambda: ai,
    )
    plan = await generate_research_plan(brief={"client": {"name": "Acme"}})
    assert plan == {"queries": ["q1", "q2", "q3"], "rationale": "because reasons"}


async def test_generate_research_plan_calls_haiku_tier(monkeypatch):
    ai = _StubAI({"queries": [], "rationale": ""})
    monkeypatch.setattr(
        "app.services.research_planner.get_ai_service", lambda: ai,
    )
    await generate_research_plan(brief={"client": {"name": "Acme"}})
    kwargs = ai.complete_json.await_args.kwargs
    assert kwargs["tier"] == Tier.FAST
    assert "research planner" in kwargs["system"].lower()
    assert "Acme" in kwargs["prompt"]


async def test_generate_benchmarks_plan_calls_haiku_with_benchmarks_system(monkeypatch):
    ai = _StubAI({"queries": ["price q"], "rationale": "why"})
    monkeypatch.setattr(
        "app.services.research_planner.get_ai_service", lambda: ai,
    )
    plan = await generate_benchmarks_plan(
        brief={"project": {"deliverables": [{"category": "Logo"}]}},
    )
    assert plan == {"queries": ["price q"], "rationale": "why"}
    kwargs = ai.complete_json.await_args.kwargs
    assert kwargs["tier"] == Tier.FAST
    assert "benchmark" in kwargs["system"].lower()
    # The deliverable category should be visible in the prompt for grounding.
    assert "Logo" in kwargs["prompt"]

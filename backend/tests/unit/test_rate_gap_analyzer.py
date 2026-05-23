from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

import app.services.ai.rate_gap_analyzer as rga
from app.services.ai.rate_gap_analyzer import analyze_gaps


@pytest.mark.asyncio
async def test_analyze_gaps_returns_lists_from_llm(monkeypatch):
    """The analyzer asks Claude to identify needed roles + offerings from the brief
    and returns them as plain lists. JSON parsing is delegated to AIService.complete_json."""
    fake_ai = AsyncMock()
    fake_ai.complete_json = AsyncMock(return_value={
        "needed_roles": ["senior_strategist", "junior_designer"],
        "needed_offerings": ["annual_retainer"],
    })
    monkeypatch.setattr(rga, "get_ai_service", lambda: fake_ai)

    result = await analyze_gaps({
        "client": {"name": "Horlicks"},
        "deliverables": ["Year-long brand campaign", "Monthly content"],
    })

    assert result == {
        "needed_roles": ["senior_strategist", "junior_designer"],
        "needed_offerings": ["annual_retainer"],
    }
    assert fake_ai.complete_json.await_count == 1


@pytest.mark.asyncio
async def test_analyze_gaps_returns_empty_on_llm_failure(monkeypatch):
    """If the LLM call raises, the analyzer logs and returns empty lists rather
    than blocking the pipeline. The cost-model fallback is the safety net."""
    fake_ai = AsyncMock()
    fake_ai.complete_json = AsyncMock(side_effect=RuntimeError("bedrock 5xx"))
    monkeypatch.setattr(rga, "get_ai_service", lambda: fake_ai)

    result = await analyze_gaps({"client": {"name": "Acme"}})

    assert result == {"needed_roles": [], "needed_offerings": []}


@pytest.mark.asyncio
async def test_analyze_gaps_returns_empty_on_malformed_response(monkeypatch):
    """If the LLM returns something that is not the expected shape, treat as no gaps."""
    fake_ai = AsyncMock()
    fake_ai.complete_json = AsyncMock(return_value={"unexpected": "shape"})
    monkeypatch.setattr(rga, "get_ai_service", lambda: fake_ai)

    result = await analyze_gaps({"client": {"name": "Acme"}})

    assert result == {"needed_roles": [], "needed_offerings": []}

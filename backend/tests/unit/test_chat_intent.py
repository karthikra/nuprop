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
    intent = await _run(monkeypatch, {
        "kind": "re_run_phase", "phase": "research", "confidence": 0.3,
    })
    assert intent["kind"] == "unknown"


@pytest.mark.asyncio
async def test_unparseable_model_output_becomes_unknown(monkeypatch):
    intent = await _run(monkeypatch, {"kind": "delete_everything", "confidence": 0.99})
    assert intent["kind"] == "unknown"


@pytest.mark.asyncio
async def test_invalid_field_for_edit_cost_item_becomes_unknown(monkeypatch):
    intent = await _run(monkeypatch, {
        "kind": "edit_cost_item", "deliverable": "Logo",
        "field": "color", "value": 3, "confidence": 0.9,
    })
    assert intent["kind"] == "unknown"


@pytest.mark.asyncio
async def test_llm_exception_becomes_unknown(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.chat_intent.get_ai_service",
        lambda: AsyncMock(complete_json=AsyncMock(side_effect=ValueError("bad json"))),
    )
    intent = await classify_intent(
        user_message="x", current_phase="research", proposal_state_hint=_hint(),
    )
    assert intent["kind"] == "unknown"

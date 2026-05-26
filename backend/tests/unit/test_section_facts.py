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

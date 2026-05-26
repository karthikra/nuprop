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

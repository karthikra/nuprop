from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.ai.cost_model_builder import CostModelBuilder


@pytest.mark.asyncio
async def test_build_uses_override_when_present(monkeypatch):
    """When rate_card_override is set, CostModelBuilder uses it directly
    and tags the result with source='override'."""
    brief = {"deliverables": [{"name": "Strategy doc", "category": "strategy"}]}
    override = {
        "hourly_rates": {"senior_strategist": 5000},
        "offerings": {"strategy_pack": {"name": "Strategy Pack", "base_price": 200000}},
    }

    builder = CostModelBuilder()
    monkeypatch.setattr(builder, "_ai_match", AsyncMock(return_value=[]))
    model = await builder.build(
        brief=brief,
        rate_card_row=None,
        template_config={},
        rate_card_override=override,
    )

    assert model.source == "override"


@pytest.mark.asyncio
async def test_build_uses_agency_when_no_override(monkeypatch):
    """Without an override, fall back to the agency rate card."""
    brief = {"deliverables": []}
    agency_rc = MagicMock()
    agency_rc.offerings = {"x": {"name": "x", "base_price": 1}}
    agency_rc.hourly_rates = {"r": 100}

    builder = CostModelBuilder()
    monkeypatch.setattr(builder, "_ai_match", AsyncMock(return_value=[]))
    model = await builder.build(
        brief=brief,
        rate_card_row=agency_rc,
        template_config={},
        rate_card_override=None,
    )

    assert model.source == "agency"


@pytest.mark.asyncio
async def test_build_uses_fallback_when_neither():
    """Without override or agency rate card, fall back to heuristic model."""
    builder = CostModelBuilder()
    model = await builder.build(
        brief={"deliverables": []},
        rate_card_row=None,
        template_config={},
        rate_card_override=None,
    )

    assert model.source == "fallback"

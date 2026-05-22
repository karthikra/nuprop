from __future__ import annotations

import pytest

from app.services.ai.cost_model_builder import CostModel


def _make_empty_cost_model() -> CostModel:
    """Construct a valid empty CostModel with all fields the pipeline reads."""
    return CostModel(
        line_items=[],
        subtotal=0,
        discount_percent=0.0,
        discount_amount=0,
        total=0,
        gst_rate=0.18,
        gst_amount=0,
        grand_total=0,
        currency="INR",
        multipliers_applied=[],
        tiered={},
        pricing_notes="",
    )


@pytest.mark.asyncio
async def test_build_cost_model_passes_merged_config(make_proposal_db, db, monkeypatch):
    """build_cost_model routes proposal.preferences through _merge_preferences_into_config
    so discount_tags reach CostModelBuilder as cost_model.default_multipliers."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(
        proposal.id, preferences={"discount_tags": ["annual_bundle"]},
    )
    await db.commit()

    captured = {}

    async def fake_build(self, **kwargs):
        captured.update(kwargs)
        return _make_empty_cost_model()

    monkeypatch.setattr(
        "app.services.ai.cost_model_builder.CostModelBuilder.build", fake_build
    )

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.build_cost_model(proposal.id)

    cfg = captured.get("template_config") or {}
    assert cfg.get("cost_model", {}).get("default_multipliers") == ["annual_bundle"]


@pytest.mark.asyncio
async def test_build_cost_model_empty_preferences_no_op(make_proposal_db, db, monkeypatch):
    """Empty preferences → merged config carries no spurious cost_model keys."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    # preferences defaults to {} — leave it.

    captured = {}

    async def fake_build(self, **kwargs):
        captured.update(kwargs)
        return _make_empty_cost_model()

    monkeypatch.setattr(
        "app.services.ai.cost_model_builder.CostModelBuilder.build", fake_build
    )

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.build_cost_model(proposal.id)

    cfg = captured.get("template_config")
    # With no template config + empty prefs, the merged config has no discount_tags-derived key.
    assert (cfg or {}).get("cost_model", {}).get("default_multipliers") is None

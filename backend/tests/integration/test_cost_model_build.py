"""Integration tests for CostModelBuilder.build against a real DB session.

With ``ANTHROPIC_API_KEY`` empty the builder takes the naive (no-LLM) matching
path, so these tests are deterministic and make no network calls.
"""

from __future__ import annotations

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.rate_card_repo import RateCardRepository
from app.services.ai.cost_model_builder import CostModelBuilder


async def _agency_with_rate_card(db):
    agency = await AgencyRepository(db).create(name="CM Agency", slug="cm-agency")
    await RateCardRepository(db).create(
        agency_id=agency.id,
        version="v1",
        is_active=True,
        offerings={
            "branding": {
                "packages": {
                    "logo_pkg": {"base": 150000, "description": "logo design and brand mark"},
                    "guidelines_pkg": {"base": 300000, "description": "complete brand guidelines document"},
                }
            }
        },
        hourly_rates={"design": 5000},
        multipliers={
            "urgency_rush": {"value": 1.5},
            "existing_client": {"value": 0.9},
            "annual_bundle": {"value": 0.85},
        },
    )
    await db.commit()
    return agency


async def test_build_returns_fallback_when_no_rate_card(db):
    agency = await AgencyRepository(db).create(name="No RC", slug="no-rc")
    await db.commit()
    model = await CostModelBuilder().build(
        brief={"project": {"deliverables": [{"category": "Logo", "quantity": 1}]}},
        db=db,
        agency_id=str(agency.id),
    )
    assert "rate card" in model.pricing_notes.lower()


async def test_build_naive_matches_deliverables_to_packages(db):
    agency = await _agency_with_rate_card(db)
    builder = CostModelBuilder()
    model = await builder.build(
        brief={"project": {"deliverables": [
            {"category": "logo design", "details": "brand mark", "quantity": 1},
        ]}},
        db=db,
        agency_id=str(agency.id),
    )
    assert len(model.line_items) == 1
    assert model.line_items[0].unit_cost > 0
    assert model.subtotal > 0
    # GST is 18% of the (post-discount) total, rounded up to nearest 10k
    assert model.gst_amount == builder._round_price(model.total * 0.18)
    assert model.grand_total == model.total + model.gst_amount
    # speculative tiered pricing is always pre-computed
    assert set(model.tiered) == {"essential", "standard", "premium"}


async def test_build_applies_rush_multiplier_from_timeline(db):
    agency = await _agency_with_rate_card(db)
    model = await CostModelBuilder().build(
        brief={"project": {
            "deliverables": [{"category": "logo design", "details": "mark", "quantity": 1}],
            "timeline": "rush — needed in 2 weeks",
        }},
        db=db,
        agency_id=str(agency.id),
    )
    assert "urgency_rush" in model.multipliers_applied


async def test_build_applies_existing_client_multiplier(db):
    agency = await _agency_with_rate_card(db)
    model = await CostModelBuilder().build(
        brief={
            "project": {"deliverables": [{"category": "logo design", "details": "m", "quantity": 1}]},
            "context": {"relationship": "existing_client"},
        },
        db=db,
        agency_id=str(agency.id),
    )
    assert "existing_client" in model.multipliers_applied


async def test_build_applies_annual_bundle_discount(db):
    agency = await _agency_with_rate_card(db)
    model = await CostModelBuilder().build(
        brief={"project": {
            "deliverables": [{"category": "logo design", "details": "m", "quantity": 1}],
            "timeline": "12 month annual retainer",
        }},
        db=db,
        agency_id=str(agency.id),
    )
    assert model.discount_percent > 0
    assert model.discount_amount > 0

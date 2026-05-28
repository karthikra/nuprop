"""Unit tests for app.services.ai.cost_model_builder — pure pricing logic.

The AI mapping path needs a configured LLM + DB; the ``build()`` integration is
covered in tests/integration/test_cost_model_build.py. Here we test the pure
helpers and the naive (no-LLM) matching path.
"""

from __future__ import annotations

from app.services.ai.cost_model_builder import CostLineItem, CostModel, CostModelBuilder


def test_round_price_rounds_up_to_nearest_10k():
    assert CostModelBuilder._round_price(0) == 0
    assert CostModelBuilder._round_price(1) == 10_000
    assert CostModelBuilder._round_price(10_000) == 10_000
    assert CostModelBuilder._round_price(10_001) == 20_000
    assert CostModelBuilder._round_price(95_000) == 100_000


def test_build_package_index_flattens_offerings_and_skips_non_dicts():
    builder = CostModelBuilder()
    offerings = {
        "branding": {"packages": {"logo": {"base": 150_000, "description": "logo design"}}},
        "video": {"packages": {"corp": {"base": 400_000, "description": "corporate video"}}},
        "broken": "not-a-dict",  # must be ignored, not crash
    }
    idx = builder._build_package_index(offerings)
    assert set(idx) == {"logo", "corp"}
    assert idx["logo"]["base"] == 150_000


def test_naive_match_finds_keyword_match():
    builder = CostModelBuilder()
    index = {"brand_pkg": {"base": 200_000, "description": "complete brand guidelines and identity"}}
    items = builder._naive_match(
        [{"category": "Brand guidelines", "details": "full identity system", "quantity": 1}],
        index,
    )
    assert len(items) == 1
    assert items[0].package_id == "brand_pkg"
    assert items[0].unit_cost == 200_000
    assert items[0].total == 200_000
    assert items[0].match_quality == "close"


def test_naive_match_falls_back_to_custom_estimate():
    builder = CostModelBuilder()
    items = builder._naive_match(
        [{"category": "Underwater basket weaving", "details": "", "quantity": 2}],
        {"brand_pkg": {"base": 200_000, "description": "brand identity"}},
    )
    assert len(items) == 1
    assert items[0].package_id is None
    assert items[0].package_name == "Custom estimate"
    assert items[0].total == 200_000  # 100_000 fallback unit cost * quantity 2


def test_fallback_model_with_no_deliverables_is_empty():
    builder = CostModelBuilder()
    model = builder._fallback_model({"project": {"deliverables": []}})
    assert model.line_items == []
    assert "rate card" in model.pricing_notes.lower()


def test_fallback_model_shells_out_each_deliverable_at_zero_cost():
    builder = CostModelBuilder()
    model = builder._fallback_model(
        {"project": {"deliverables": [{"category": "Logo", "quantity": 1}]}}
    )
    assert len(model.line_items) == 1
    assert model.line_items[0].unit_cost == 0


def test_build_tiered_structure_and_premium_uplift():
    builder = CostModelBuilder()
    items = [
        CostLineItem(
            deliverable="Logo", package_id="p1", package_name="Logo pkg",
            match_quality="exact", quantity=1, unit_cost=100_000, total=100_000,
        ),
    ]
    tiered = builder._build_tiered(items, discount_percent=0.0)
    assert set(tiered) == {"essential", "standard", "premium"}
    assert tiered["standard"]["subtotal"] == 100_000
    # premium = +20% uplift, rounded up to nearest 10k
    assert tiered["premium"]["line_items"][0]["unit_cost"] == 120_000
    # GST is always 18%, rounded up to nearest 10k
    expected_gst = builder._round_price(100_000 * 0.18)
    assert tiered["standard"]["gst_amount"] == expected_gst
    assert tiered["standard"]["grand_total"] == 100_000 + expected_gst


def test_build_tiered_essential_skips_hourly_items():
    builder = CostModelBuilder()
    items = [
        CostLineItem("A", "p1", "exact pkg", "exact", 1, 100_000, 100_000),
        CostLineItem("B", None, "hourly est", "hourly", 1, 100_000, 100_000),
    ]
    tiered = builder._build_tiered(items, 0.0)
    assert len(tiered["essential"]["line_items"]) == 1  # only the exact match
    assert len(tiered["standard"]["line_items"]) == 2


async def test_ai_match_synthesizes_package_name_when_null_or_missing():
    """The AI may return ``"package_name": null`` (or omit the key) for a line
    item. ``dict.get("package_name", "")`` returns ``None`` on an explicit JSON
    null, which crashes downstream formatting (``None[:40]``). The builder must
    synthesize a non-empty ``"Custom (<deliverable>)"`` label instead.
    """
    builder = CostModelBuilder()

    async def _fake_complete_json(*args, **kwargs):
        return [
            # explicit JSON null for package_name
            {"deliverable": "Brand workshop", "package_id": None, "package_name": None,
             "match_quality": "hourly", "quantity": 1, "unit_cost": 80_000},
            # package_name key omitted entirely
            {"deliverable": "Discovery sprint", "package_id": None,
             "match_quality": "hourly", "quantity": 1, "unit_cost": 60_000},
            # empty-string package_name
            {"deliverable": "Audit", "package_id": None, "package_name": "",
             "match_quality": "hourly", "quantity": 1, "unit_cost": 40_000},
        ]

    builder._llm.complete_json = _fake_complete_json

    items = await builder._ai_match(
        deliverables=[{"category": "Brand workshop"}],
        package_index={},
        hourly_rates={},
    )

    assert len(items) == 3
    for item in items:
        assert item.package_name, "package_name must never be None or empty"
        assert item.package_name.startswith("Custom (")
    assert items[0].package_name == "Custom (Brand workshop)"
    assert items[1].package_name == "Custom (Discovery sprint)"
    assert items[2].package_name == "Custom (Audit)"


def test_model_to_dict_roundtrips_line_items_and_totals():
    model = CostModel(
        line_items=[CostLineItem("Logo", "p1", "Logo pkg", "exact", 2, 50_000, 100_000)],
        subtotal=100_000, total=100_000, gst_amount=18_000, grand_total=118_000,
        multipliers_applied=["existing_client"],
    )
    d = CostModelBuilder.model_to_dict(model)
    assert d["subtotal"] == 100_000
    assert d["grand_total"] == 118_000
    assert d["multipliers_applied"] == ["existing_client"]
    assert d["line_items"][0]["deliverable"] == "Logo"
    assert d["line_items"][0]["quantity"] == 2
    assert d["source"] == "fallback"

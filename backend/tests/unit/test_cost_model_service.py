from __future__ import annotations

import pytest

from app.services.cost_model_service import (
    CostItemEditError, apply_cost_item_edit, find_line_item_index,
)


def _model():
    return {
        "line_items": [
            {"deliverable": "Logo", "quantity": 1, "unit_cost": 100000, "total": 100000},
            {"deliverable": "Brand Guidelines", "quantity": 2, "unit_cost": 50000, "total": 100000},
        ],
        "discount_amount": 0,
    }


def test_edit_quantity_recalculates_item_total():
    out = apply_cost_item_edit(_model(), index=0, field="quantity", value=3)
    assert out["line_items"][0]["total"] == 300000


def test_edit_recomputes_grand_total_consistently():
    """grand_total must be internally consistent with the handler's own
    formula. We don't hard-code the GST number here; instead we assert the
    relationship the handler defines."""
    out = apply_cost_item_edit(_model(), index=0, field="quantity", value=3)
    # subtotal should be the sum of line-item totals
    assert out["subtotal"] == sum(li["total"] for li in out["line_items"])
    # grand_total should be >= subtotal (GST added) and an int
    assert isinstance(out["grand_total"], int) or isinstance(out["grand_total"], float)
    assert out["grand_total"] >= out["subtotal"] - out.get("discount_amount", 0)


def test_edit_exact_gst_and_grand_total():
    """Exact-number assertion mirroring the handler formula:
    subtotal = 400000, discount_percent absent -> 0, gst = int(400000 * 0.18)."""
    out = apply_cost_item_edit(_model(), index=0, field="quantity", value=3)
    assert out["subtotal"] == 400000
    assert out["discount_amount"] == 0
    assert out["total"] == 400000
    assert out["gst_amount"] == 72000  # int(400000 * 0.18)
    assert out["grand_total"] == 472000


def test_invalid_field_raises():
    with pytest.raises(CostItemEditError):
        apply_cost_item_edit(_model(), index=0, field="color", value=3)


def test_out_of_range_index_raises():
    with pytest.raises(CostItemEditError):
        apply_cost_item_edit(_model(), index=9, field="quantity", value=3)


def test_missing_line_items_raises():
    with pytest.raises(CostItemEditError):
        apply_cost_item_edit({}, index=0, field="quantity", value=3)


def test_find_line_item_index_is_case_insensitive():
    assert find_line_item_index(_model(), "logo") == 0
    assert find_line_item_index(_model(), "BRAND guidelines") == 1
    assert find_line_item_index(_model(), "nope") is None


def test_apply_cost_item_edit_does_not_mutate_input():
    model = _model()
    snapshot = {"line_items": [dict(li) for li in model["line_items"]]}
    apply_cost_item_edit(model, index=0, field="quantity", value=5)
    # the original dict must be unchanged
    assert model["line_items"][0]["quantity"] == snapshot["line_items"][0]["quantity"]
    assert model["line_items"][0]["total"] == snapshot["line_items"][0]["total"]

"""Pure cost-model edit logic shared by the cost-model PATCH route and the
chat-intent dispatcher.

No DB, no transport, no broadcast — just dict-in/dict-out transformation plus a
lookup helper. The recalculation here is transcribed exactly from the inline
logic that previously lived in ``update_cost_model_item`` (chat.py): GST is 18%
applied AFTER a percentage discount.
"""

from __future__ import annotations

import copy

ALLOWED_FIELDS = ("quantity", "unit_cost")
GST_RATE = 0.18


class CostItemEditError(ValueError):
    """Raised for an invalid index, field, or a missing/invalid cost model."""


def apply_cost_item_edit(
    cost_model: dict, *, index: int, field: str, value: int
) -> dict:
    """Apply a single line-item edit and recompute all totals.

    Returns a NEW dict and does not mutate the input ``cost_model`` — the input
    is deep-copied first so the caller's live object (e.g. a SQLAlchemy
    attribute) is never touched, even on a mid-operation exception. Transcribes
    the handler's formula exactly: ``item["total"] = unit_cost * quantity``;
    ``subtotal`` is the sum of line-item totals; the discount is a percentage
    from ``discount_percent`` (default 0) applied to the subtotal; GST is 18% of
    the post-discount total; ``grand_total`` = post-discount total + GST.

    Raises ``CostItemEditError`` for an unknown field, a missing
    ``line_items``, or an out-of-range index.
    """
    if not cost_model or "line_items" not in cost_model:
        raise CostItemEditError("No cost model to update")

    cost_model = copy.deepcopy(cost_model)

    items = cost_model["line_items"]
    if index < 0 or index >= len(items):
        raise CostItemEditError("Invalid line item index")

    item = items[index]
    if field == "quantity":
        item["quantity"] = value
        item["total"] = item["unit_cost"] * value
    elif field == "unit_cost":
        item["unit_cost"] = value
        item["total"] = value * item["quantity"]
    else:
        raise CostItemEditError(f"Invalid field: {field}")

    # Recalculate totals
    subtotal = sum(i["total"] for i in items)
    discount_pct = cost_model.get("discount_percent", 0)
    discount_amt = int(subtotal * discount_pct / 100)
    total = subtotal - discount_amt
    gst = int(total * GST_RATE)

    cost_model["subtotal"] = subtotal
    cost_model["discount_amount"] = discount_amt
    cost_model["total"] = total
    cost_model["gst_amount"] = gst
    cost_model["grand_total"] = total + gst

    return cost_model


def find_line_item_index(cost_model: dict, deliverable: str) -> int | None:
    """Return the index of the line item whose ``deliverable`` matches
    ``deliverable`` case-insensitively, or ``None`` if there is no match."""
    if not cost_model or "line_items" not in cost_model:
        return None

    target = deliverable.strip().lower()
    for idx, item in enumerate(cost_model["line_items"]):
        name = item.get("deliverable")
        if name is not None and name.strip().lower() == target:
            return idx
    return None

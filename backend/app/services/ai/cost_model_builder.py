from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.rate_card import RateCard
from app.infrastructure.external.anthropic_client import AnthropicClient

MAPPING_PROMPT = """You are a cost modelling assistant for a design agency proposal tool.

Given a client brief's deliverables and a rate card (JSON), map each deliverable to the best matching rate card package.

## Instructions:
1. For each deliverable in the brief, find the BEST matching package in the rate card by comparing the deliverable description against package descriptions.
2. If no package matches, estimate using hourly rates × estimated hours.
3. Return a JSON array of line items.

## Output format (JSON array):
```json
[
  {
    "deliverable": "the deliverable name from the brief",
    "package_id": "rate card package key or null if hourly estimate",
    "package_name": "matched package description",
    "match_quality": "exact | close | hourly",
    "quantity": 1,
    "unit_cost": 150000,
    "estimated_hours": null,
    "hourly_rate_key": null,
    "notes": "why this match was chosen"
  }
]
```

Be precise with package matching. Use the `description` field to match, not just the key name. If the brief says "brand guidelines", match to the package whose description mentions "brand guideline". If the brief says "corporate video", match to the video package that best fits the scope described."""


@dataclass
class CostLineItem:
    deliverable: str
    package_id: str | None
    package_name: str
    match_quality: str  # exact, close, hourly
    quantity: int
    unit_cost: int
    total: int
    estimated_hours: int | None = None
    hourly_rate_key: str | None = None
    notes: str = ""
    market_low: int | None = None
    market_high: int | None = None


@dataclass
class CostModel:
    line_items: list[CostLineItem] = field(default_factory=list)
    subtotal: int = 0
    discount_percent: float = 0.0
    discount_amount: int = 0
    total: int = 0
    gst_rate: float = 0.18
    gst_amount: int = 0
    grand_total: int = 0
    currency: str = "INR"
    multipliers_applied: list[str] = field(default_factory=list)
    pricing_notes: str = ""


class CostModelBuilder:
    def __init__(self):
        self._llm = AnthropicClient()

    async def build(
        self,
        brief: dict,
        db: AsyncSession,
        agency_id: str,
        benchmarks_md: str | None = None,
        template_config: dict | None = None,
    ) -> CostModel:
        """Build a cost model from the brief and rate card."""
        # Load the active rate card
        result = await db.execute(
            select(RateCard)
            .where(RateCard.agency_id == agency_id, RateCard.is_active == True)
            .limit(1)
        )
        rate_card_row = result.scalar_one_or_none()

        if not rate_card_row:
            return self._fallback_model(brief)

        rate_card = {
            "offerings": rate_card_row.offerings,
            "hourly_rates": rate_card_row.hourly_rates,
            "multipliers": rate_card_row.multipliers,
            "pass_through_markup": rate_card_row.pass_through_markup,
            "standard_options": rate_card_row.standard_options,
            "standard_revisions": rate_card_row.standard_revisions,
        }

        deliverables = brief.get("project", {}).get("deliverables", [])
        if not deliverables:
            return self._fallback_model(brief)

        # Flatten rate card packages into a lookup
        package_index = self._build_package_index(rate_card["offerings"])

        # Use AI to map deliverables to packages
        if self._llm.is_configured:
            line_items = await self._ai_match(deliverables, package_index, rate_card["hourly_rates"])
        else:
            line_items = self._naive_match(deliverables, package_index)

        # Apply multipliers
        multipliers_applied = []
        multiplier_factor = 1.0

        if template_config:
            default_mults = template_config.get("cost_model", {}).get("default_multipliers", [])
            for mult_key in default_mults:
                mult_info = rate_card.get("multipliers", {}).get(mult_key, {})
                if mult_info:
                    multiplier_factor *= mult_info.get("value", 1.0)
                    multipliers_applied.append(mult_key)

        # Check brief signals for multipliers
        timeline = brief.get("project", {}).get("timeline", "").lower()
        if "rush" in timeline or "urgent" in timeline:
            rush = rate_card.get("multipliers", {}).get("urgency_rush", {})
            if rush and "urgency_rush" not in multipliers_applied:
                multiplier_factor *= rush.get("value", 1.5)
                multipliers_applied.append("urgency_rush")

        budget_signal = brief.get("project", {}).get("budget_signal", "").lower()
        relationship = brief.get("context", {}).get("relationship", "")
        if relationship == "existing_client":
            existing = rate_card.get("multipliers", {}).get("existing_client", {})
            if existing and "existing_client" not in multipliers_applied:
                multiplier_factor *= existing.get("value", 0.95)
                multipliers_applied.append("existing_client")

        # Calculate totals
        for item in line_items:
            item.unit_cost = self._round_price(item.unit_cost * multiplier_factor)
            item.total = item.unit_cost * item.quantity

        subtotal = sum(item.total for item in line_items)

        # Bundle discount for year-long engagements
        discount_percent = 0.0
        if "year" in timeline or "12 month" in timeline or "annual" in timeline:
            annual_mult = rate_card.get("multipliers", {}).get("annual_bundle", {})
            if annual_mult:
                discount_percent = round((1 - annual_mult.get("value", 0.88)) * 100)

        discount_amount = self._round_price(subtotal * discount_percent / 100)
        total = subtotal - discount_amount
        gst_rate = rate_card_row.pass_through_markup if rate_card_row else 0.18
        gst_amount = self._round_price(total * 0.18)  # GST always 18%
        grand_total = total + gst_amount

        return CostModel(
            line_items=line_items,
            subtotal=subtotal,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            total=total,
            gst_rate=0.18,
            gst_amount=gst_amount,
            grand_total=grand_total,
            currency="INR",
            multipliers_applied=multipliers_applied,
        )

    def _build_package_index(self, offerings: dict) -> dict[str, dict]:
        """Flatten offerings into {package_id: {base, description, ...}}."""
        index = {}
        for offering_key, offering in offerings.items():
            if not isinstance(offering, dict):
                continue
            packages = offering.get("packages", {})
            for pkg_id, pkg in packages.items():
                if isinstance(pkg, dict):
                    index[pkg_id] = pkg
        return index

    async def _ai_match(
        self,
        deliverables: list[dict],
        package_index: dict[str, dict],
        hourly_rates: dict,
    ) -> list[CostLineItem]:
        """Use Claude to map deliverables to rate card packages."""
        # Compact the rate card for the prompt
        compact_packages = {
            k: {"base": v.get("base", 0), "description": v.get("description", "")}
            for k, v in package_index.items()
        }

        brief_deliverables = json.dumps(deliverables, indent=2)
        rate_card_json = json.dumps(compact_packages, indent=2)
        hourly_json = json.dumps(hourly_rates, indent=2)

        try:
            result = await self._llm.complete_json(
                system=MAPPING_PROMPT,
                messages=[{
                    "role": "user",
                    "content": (
                        f"## Deliverables from brief:\n```json\n{brief_deliverables}\n```\n\n"
                        f"## Rate card packages:\n```json\n{rate_card_json}\n```\n\n"
                        f"## Hourly rates:\n```json\n{hourly_json}\n```"
                    ),
                }],
                max_tokens=4096,
            )
        except Exception:
            return self._naive_match(deliverables, package_index)

        items = []
        if isinstance(result, list):
            mapping = result
        elif isinstance(result, dict) and "line_items" in result:
            mapping = result["line_items"]
        else:
            mapping = [result] if isinstance(result, dict) else []

        for m in mapping:
            pkg_id = m.get("package_id")
            unit_cost = m.get("unit_cost", 0)

            # If matched to a package, use the rate card price
            if pkg_id and pkg_id in package_index:
                unit_cost = package_index[pkg_id].get("base", unit_cost)

            items.append(CostLineItem(
                deliverable=m.get("deliverable", "Unknown"),
                package_id=pkg_id,
                package_name=m.get("package_name", ""),
                match_quality=m.get("match_quality", "close"),
                quantity=m.get("quantity", 1),
                unit_cost=unit_cost,
                total=unit_cost * m.get("quantity", 1),
                estimated_hours=m.get("estimated_hours"),
                hourly_rate_key=m.get("hourly_rate_key"),
                notes=m.get("notes", ""),
            ))

        return items

    def _naive_match(self, deliverables: list[dict], package_index: dict) -> list[CostLineItem]:
        """Fallback: simple keyword matching without AI."""
        items = []
        for d in deliverables:
            cat = d.get("category", "").lower()
            details = d.get("details", "").lower()
            search_text = f"{cat} {details}"
            quantity = d.get("quantity", 1)

            best_pkg_id = None
            best_pkg = None
            best_score = 0

            for pkg_id, pkg in package_index.items():
                desc = pkg.get("description", "").lower()
                score = sum(1 for word in search_text.split() if word in desc and len(word) > 3)
                if score > best_score:
                    best_score = score
                    best_pkg_id = pkg_id
                    best_pkg = pkg

            if best_pkg and best_score > 0:
                unit_cost = best_pkg.get("base", 100000)
                items.append(CostLineItem(
                    deliverable=d.get("category", "Unknown"),
                    package_id=best_pkg_id,
                    package_name=best_pkg.get("description", ""),
                    match_quality="close" if best_score >= 2 else "hourly",
                    quantity=quantity,
                    unit_cost=unit_cost,
                    total=unit_cost * quantity,
                ))
            else:
                items.append(CostLineItem(
                    deliverable=d.get("category", "Unknown"),
                    package_id=None,
                    package_name="Custom estimate",
                    match_quality="hourly",
                    quantity=quantity,
                    unit_cost=100000,
                    total=100000 * quantity,
                    estimated_hours=25,
                    notes="No matching package found",
                ))

        return items

    def _fallback_model(self, brief: dict) -> CostModel:
        """When no rate card exists, return a shell model."""
        deliverables = brief.get("project", {}).get("deliverables", [])
        items = [
            CostLineItem(
                deliverable=d.get("category", "Unknown"),
                package_id=None,
                package_name="No rate card configured",
                match_quality="hourly",
                quantity=d.get("quantity", 1),
                unit_cost=0,
                total=0,
                notes="Configure a rate card to get pricing",
            )
            for d in deliverables
        ]
        return CostModel(line_items=items, pricing_notes="No rate card configured. Set up your rate card in Settings.")

    @staticmethod
    def _round_price(amount: float) -> int:
        """Round to nearest ₹10,000."""
        return int(math.ceil(amount / 10000) * 10000)

    @staticmethod
    def model_to_dict(model: CostModel) -> dict:
        """Convert CostModel to a JSON-serializable dict."""
        return {
            "line_items": [
                {
                    "deliverable": item.deliverable,
                    "package_id": item.package_id,
                    "package_name": item.package_name,
                    "match_quality": item.match_quality,
                    "quantity": item.quantity,
                    "unit_cost": item.unit_cost,
                    "total": item.total,
                    "estimated_hours": item.estimated_hours,
                    "notes": item.notes,
                    "market_low": item.market_low,
                    "market_high": item.market_high,
                }
                for item in model.line_items
            ],
            "subtotal": model.subtotal,
            "discount_percent": model.discount_percent,
            "discount_amount": model.discount_amount,
            "total": model.total,
            "gst_rate": model.gst_rate,
            "gst_amount": model.gst_amount,
            "grand_total": model.grand_total,
            "currency": model.currency,
            "multipliers_applied": model.multipliers_applied,
            "pricing_notes": model.pricing_notes,
        }

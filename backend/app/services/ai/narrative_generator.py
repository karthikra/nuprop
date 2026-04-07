from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from app.infrastructure.external.anthropic_client import AnthropicClient

LETTER_STRATEGIES = {
    "confident": {
        "description": "Bold, assertive, positions the agency as the obvious choice. Leads with a strong point of view.",
        "contrast": "warm",
    },
    "warm": {
        "description": "Empathetic, human, focuses on understanding the client's world before offering solutions.",
        "contrast": "confident",
    },
    "research_heavy": {
        "description": "Data-driven, analytical, opens with specific findings about the client's situation.",
        "contrast": "relationship_builder",
    },
    "technical_showcase": {
        "description": "Process-led, methodical, demonstrates expertise through how the work will be done.",
        "contrast": "warm",
    },
    "relationship_builder": {
        "description": "Partnership-focused, collaborative, emphasizes long-term value and working together.",
        "contrast": "research_heavy",
    },
}

AVOID_WORDS = "leverage, synergy, best-in-class, utilize, holistic, cutting-edge, world-class, thought leadership, seamlessly, robust, scalable, end-to-end, bespoke, paradigm, we look forward to hearing from you, please find attached, our team of experienced professionals"

COVERING_LETTER_SYSTEM = """You are writing a proposal covering letter for {agency_name}.

{voice_section}

STRATEGY: {strategy}
{strategy_description}

OPENING: {opening_instruction}

RULES:
1. Open with the CLIENT. First 2-3 paragraphs entirely about them — their story, their challenge, their opportunity. Do NOT mention the agency until paragraph 3 or later.
2. Reference at least ONE specific fact from the research. A date, a number, a name — proof you did homework.
3. Middle: position the agency by telling a story or drawing a parallel. Do NOT list credentials as bullets.
4. Close with a specific CTA — propose a day, time, format. "Would Thursday at 3pm work for a 30-minute walkthrough?"
5. Sign off with FIRST NAME ONLY.
6. Length: 400-600 words.
7. NEVER use: {avoid_words}
8. Active voice. Short sentences. No sentence over 25 words.

CLIENT: {client_name} ({industry})
PROJECT: {project_type}
DELIVERABLES: {deliverables_summary}
BUDGET: {budget_signal}
TIMELINE: {timeline}
RELATIONSHIP: {relationship}

RESEARCH:
{research}

Write the letter now. Start directly with the client's name or situation."""

EXEC_SUMMARY_SYSTEM = """Write the executive summary of a design agency proposal.

STRUCTURE (4 paragraphs, no headers):
1. What we're proposing — engagement structure, deliverables, what the client gets
2. Why this approach — strategic reasoning, why these deliverables in this order
3. Team and process — how we work, collaboration model. 2-3 sentences.
4. Investment — total amount framed as: {pricing_framing}. {pricing_anchor}. Include total, GST, grand total.

RULES: 300-400 words. Factual, not emotional. Use real numbers. No "leverage/synergy/holistic/robust".

COST MODEL:
Subtotal: {currency}{subtotal:,} | Discount: {discount_pct}% | Total: {currency}{total:,} | GST: {currency}{gst:,} | Grand Total: {currency}{grand_total:,}

LINE ITEMS:
{line_items_summary}

CLIENT: {client_name} | PROJECT: {project_type} | AGENCY: {agency_name}"""

SCOPE_SECTION_SYSTEM = """Write a scope description for this deliverable in a design agency proposal.

DELIVERABLE: {deliverable_name}
PACKAGE: {package_name}
INCLUDES: {package_includes}
QUANTITY: {quantity}
DETAIL LEVEL: {detail_level} ({word_range} words for "What's included")

Format:
### {deliverable_name}

**What's included**
[{detail_instruction}]

**What's excluded**
[2-4 specific exclusions]

**Creative standard**
- {standard_options} initial options
- {standard_revisions} revision rounds

**Timeline**: Estimated delivery relative to project start.
**Dependencies**: 1-3 things the client must provide.

Be specific. No filler. No "leverage/synergy/holistic"."""

COST_RATIONALE_SYSTEM = """Write the cost rationale for a design agency proposal. Justify each major cost category against market benchmarks.

DEPTH: {depth} — {depth_instruction}

For each category:
### [Category]
**Market range**: What the market charges (from benchmarks).
**Our pricing**: What we charge and why.
**Our difference**: What makes our approach unique.

RULES: Use real benchmark numbers. If no data, say "Published benchmarks limited." Never fabricate. Confident tone, not defensive.

BENCHMARKS:
{benchmarks}

COST MODEL:
{cost_summary}

CLIENT: {client_name} ({industry})"""

TERMS_TEMPLATE = """## Terms & Conditions

### Payment Schedule
{payment_schedule}

### Intellectual Property
All creative intellectual property transfers to the client upon full payment for each deliverable.

### Revisions
{standard_options} initial design options and {standard_revisions} rounds of revisions are included per deliverable. Additional revisions are billed at applicable hourly rates.

### Cancellation
Either party may terminate with 30 days written notice. Work completed up to the termination date will be invoiced and is payable.

### Confidentiality
All proposal contents and pricing are confidential. Neither party will disclose the other's business information without written consent.

### GST
All amounts are exclusive of GST ({gst_rate}%). GST of {currency}{gst_amount:,} applies to the total.

### Validity
This proposal is valid for {validity_days} days from the date of issue.

---

**Client**: {client_name}
**Project**: {project_name}
**Total (excl. GST)**: {currency}{total:,}
**GST ({gst_rate}%)**: {currency}{gst_amount:,}
**Grand Total**: {currency}{grand_total:,}"""

DETAIL_LEVELS = {
    "brief": {"range": "50-100", "instruction": "Concise summary. Key points only."},
    "standard": {"range": "100-150", "instruction": "Clear description with sub-bullets for specifics."},
    "detailed": {"range": "150-250", "instruction": "Thorough with methodology, process steps, specific outputs."},
}


@dataclass
class NarrativeResult:
    covering_letter: str
    covering_letter_alt: str
    letter_strategy_primary: str
    letter_strategy_alt: str
    executive_summary: str
    scope_sections: list[dict]
    cost_rationale: str | None
    terms: str


class NarrativeGenerator:
    def __init__(self):
        self._llm = AnthropicClient()

    async def generate_all(
        self,
        brief: dict,
        research: str | None,
        benchmarks: str | None,
        cost_model: dict,
        template_config: dict | None,
        agency_name: str,
        agency_voice: str | None,
        agency_default_terms: str | None,
        agency_payment_terms: dict | None,
        agency_gst_rate: float,
        rate_card_offerings: dict | None,
        standard_options: int = 3,
        standard_revisions: int = 2,
    ) -> NarrativeResult:
        """Generate all narrative sections."""
        # Letters (parallel)
        primary, alt, p_strat, a_strat = await self.generate_covering_letters(
            brief, research or "", template_config, agency_name, agency_voice,
        )

        # Exec summary
        exec_summary = await self.generate_executive_summary(
            brief, cost_model, template_config, agency_name,
        )

        # Scope sections (parallel per deliverable)
        scope_sections = await self.generate_scope_sections(
            brief, cost_model, template_config, rate_card_offerings,
            standard_options, standard_revisions,
        )

        # Cost rationale (skip if under 10L)
        cost_rationale = None
        total = cost_model.get("total", 0)
        if total >= 1000000:
            cost_rationale = await self.generate_cost_rationale(
                brief, cost_model, benchmarks or "", template_config,
            )

        # Terms
        terms = self.generate_terms(
            brief, cost_model, agency_default_terms, agency_payment_terms,
            agency_gst_rate, standard_options, standard_revisions,
        )

        return NarrativeResult(
            covering_letter=primary,
            covering_letter_alt=alt,
            letter_strategy_primary=p_strat,
            letter_strategy_alt=a_strat,
            executive_summary=exec_summary,
            scope_sections=scope_sections,
            cost_rationale=cost_rationale,
            terms=terms,
        )

    async def generate_covering_letters(
        self, brief: dict, research: str, template_config: dict | None,
        agency_name: str, agency_voice: str | None,
    ) -> tuple[str, str, str, str]:
        """Returns (primary_text, alt_text, primary_strategy, alt_strategy)."""
        narr_cfg = (template_config or {}).get("narrative", {})
        primary_strategy = narr_cfg.get("letter_strategy", "confident")
        alt_strategy = LETTER_STRATEGIES.get(primary_strategy, {}).get("contrast", "warm")
        opening = narr_cfg.get("letter_opening_instruction",
            "Open with the CLIENT. First 2-3 paragraphs entirely about them.")
        extra_avoid = ", ".join(narr_cfg.get("letter_avoid_words", []))
        avoid = f"{AVOID_WORDS}, {extra_avoid}" if extra_avoid else AVOID_WORDS
        tone_words = ", ".join(narr_cfg.get("letter_tone_words", []))

        client = brief.get("client", {})
        project = brief.get("project", {})
        ctx = brief.get("context", {})
        deliverables = ", ".join(d.get("category", "") for d in project.get("deliverables", []))

        voice_section = f"VOICE PROFILE:\n{agency_voice}" if agency_voice else ""

        async def _gen_letter(strategy: str) -> str:
            strat_info = LETTER_STRATEGIES.get(strategy, LETTER_STRATEGIES["confident"])
            prompt = COVERING_LETTER_SYSTEM.format(
                agency_name=agency_name,
                voice_section=voice_section,
                strategy=strategy,
                strategy_description=strat_info["description"],
                opening_instruction=opening,
                avoid_words=avoid,
                client_name=client.get("name", "the client"),
                industry=client.get("industry", ""),
                project_type=project.get("type", ""),
                deliverables_summary=deliverables,
                budget_signal=project.get("budget_signal", "Not disclosed"),
                timeline=project.get("timeline", ""),
                relationship=ctx.get("relationship", "cold_pitch"),
                research=research[:3000] if research else "No research available.",
            )
            if not self._llm.is_configured:
                return f"[{strategy.upper()} LETTER — AI not configured]\n\nDear {client.get('name', 'Client')},\n\n[Covering letter content would be generated here with {strategy} tone.]"
            return await self._llm.complete(system=prompt, messages=[
                {"role": "user", "content": "Write the covering letter now."}
            ], max_tokens=2048, temperature=0.8)

        primary_text, alt_text = await asyncio.gather(
            _gen_letter(primary_strategy),
            _gen_letter(alt_strategy),
        )
        return primary_text, alt_text, primary_strategy, alt_strategy

    async def generate_executive_summary(
        self, brief: dict, cost_model: dict, template_config: dict | None,
        agency_name: str,
    ) -> str:
        cm_cfg = (template_config or {}).get("cost_model", {})
        pricing_framing = cm_cfg.get("pricing_framing", "market_rate")
        pricing_anchor = cm_cfg.get("pricing_anchor_text", "Position against market rates.")
        currency = cost_model.get("currency", "INR")
        sym = "₹" if currency == "INR" else "$"

        items_summary = "\n".join(
            f"- {i['deliverable']}: {sym}{i['total']:,}"
            for i in cost_model.get("line_items", [])
        )

        prompt = EXEC_SUMMARY_SYSTEM.format(
            pricing_framing=pricing_framing,
            pricing_anchor=pricing_anchor,
            currency=sym,
            subtotal=cost_model.get("subtotal", 0),
            discount_pct=cost_model.get("discount_percent", 0),
            total=cost_model.get("total", 0),
            gst=cost_model.get("gst_amount", 0),
            grand_total=cost_model.get("grand_total", 0),
            line_items_summary=items_summary,
            client_name=brief.get("client", {}).get("name", ""),
            project_type=brief.get("project", {}).get("type", ""),
            agency_name=agency_name,
        )

        if not self._llm.is_configured:
            return "[EXECUTIVE SUMMARY — AI not configured]"

        return await self._llm.complete(system=prompt, messages=[
            {"role": "user", "content": "Write the executive summary now."}
        ], max_tokens=1500, temperature=0.5)

    async def generate_scope_sections(
        self, brief: dict, cost_model: dict, template_config: dict | None,
        rate_card_offerings: dict | None, standard_options: int = 3,
        standard_revisions: int = 2,
    ) -> list[dict]:
        narr_cfg = (template_config or {}).get("narrative", {})
        detail_level = narr_cfg.get("scope_detail_level", "standard")
        detail_info = DETAIL_LEVELS.get(detail_level, DETAIL_LEVELS["standard"])

        # Build a package lookup for `includes` fields
        pkg_includes = {}
        if rate_card_offerings:
            for offering in rate_card_offerings.values():
                if isinstance(offering, dict):
                    for pkg_id, pkg in offering.get("packages", {}).items():
                        if isinstance(pkg, dict):
                            pkg_includes[pkg_id] = pkg.get("includes", "")

        line_items = cost_model.get("line_items", [])

        async def _gen_scope(item: dict) -> dict:
            pkg_id = item.get("package_id", "")
            includes = pkg_includes.get(pkg_id, "Standard deliverables as per scope.")

            prompt = SCOPE_SECTION_SYSTEM.format(
                deliverable_name=item.get("deliverable", ""),
                package_name=item.get("package_name", ""),
                package_includes=includes,
                quantity=item.get("quantity", 1),
                detail_level=detail_level,
                word_range=detail_info["range"],
                detail_instruction=detail_info["instruction"],
                standard_options=standard_options,
                standard_revisions=standard_revisions,
            )

            if not self._llm.is_configured:
                return {
                    "deliverable": item.get("deliverable", ""),
                    "package_name": item.get("package_name", ""),
                    "content": f"[SCOPE — AI not configured for {item.get('deliverable', '')}]",
                }

            content = await self._llm.complete(system=prompt, messages=[
                {"role": "user", "content": "Write the scope description now."}
            ], max_tokens=1024, temperature=0.4)

            return {
                "deliverable": item.get("deliverable", ""),
                "package_name": item.get("package_name", ""),
                "content": content,
            }

        # Generate in parallel (batch of 5 at a time to avoid rate limits)
        results = []
        for i in range(0, len(line_items), 5):
            batch = line_items[i:i+5]
            batch_results = await asyncio.gather(*[_gen_scope(item) for item in batch])
            results.extend(batch_results)

        return results

    async def generate_cost_rationale(
        self, brief: dict, cost_model: dict, benchmarks: str,
        template_config: dict | None,
    ) -> str:
        narr_cfg = (template_config or {}).get("narrative", {})
        depth = narr_cfg.get("rationale_depth", "standard")
        depth_instructions = {
            "light": "1-2 sentences per category. 200-300 words total.",
            "standard": "3-5 sentences per category. 400-600 words total.",
            "exhaustive": "Full paragraph per category with comparisons. 600-1000 words total.",
        }

        items_summary = "\n".join(
            f"- {i['deliverable']}: ₹{i['total']:,} ({i['match_quality']})"
            for i in cost_model.get("line_items", [])
        )

        prompt = COST_RATIONALE_SYSTEM.format(
            depth=depth,
            depth_instruction=depth_instructions.get(depth, depth_instructions["standard"]),
            benchmarks=benchmarks[:4000] if benchmarks else "No benchmark data available.",
            cost_summary=f"Total: ₹{cost_model.get('total',0):,}\n{items_summary}",
            client_name=brief.get("client", {}).get("name", ""),
            industry=brief.get("client", {}).get("industry", ""),
        )

        if not self._llm.is_configured:
            return "[COST RATIONALE — AI not configured]"

        return await self._llm.complete(system=prompt, messages=[
            {"role": "user", "content": "Write the cost rationale now."}
        ], max_tokens=3000, temperature=0.3)

    def generate_terms(
        self, brief: dict, cost_model: dict, agency_default_terms: str | None,
        agency_payment_terms: dict | None, agency_gst_rate: float,
        standard_options: int = 3, standard_revisions: int = 2,
    ) -> str:
        """Generate terms — mostly template substitution, no LLM needed."""
        client_name = brief.get("client", {}).get("name", "[Client Name]")
        project_name = brief.get("project", {}).get("type", "[Project Name]")
        currency = "₹"
        total = cost_model.get("total", 0)
        gst_amount = cost_model.get("gst_amount", 0)
        grand_total = cost_model.get("grand_total", 0)
        gst_rate_pct = int(agency_gst_rate * 100)

        schedule = agency_payment_terms or {}
        milestone = schedule.get("milestone_schedule", {"advance": 0.2, "mid_project": 0.5, "completion": 0.3})
        payment_schedule = (
            f"- {int(milestone.get('advance', 0.2)*100)}% advance upon confirmation\n"
            f"- {int(milestone.get('mid_project', 0.5)*100)}% at mid-project milestone\n"
            f"- {int(milestone.get('completion', 0.3)*100)}% upon final delivery and approval"
        )

        if agency_default_terms:
            return agency_default_terms

        return TERMS_TEMPLATE.format(
            payment_schedule=payment_schedule,
            standard_options=standard_options,
            standard_revisions=standard_revisions,
            gst_rate=gst_rate_pct,
            currency=currency,
            gst_amount=gst_amount,
            validity_days=30,
            client_name=client_name,
            project_name=project_name,
            total=total,
            grand_total=grand_total,
        )

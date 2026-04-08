from __future__ import annotations

from app.infrastructure.external.anthropic_client import AnthropicClient
from app.core.config import get_settings


BENCHMARK_SYSTEM = """You are a market research analyst specializing in agency pricing. Your job is to find published pricing benchmarks for specific service categories so a design agency can justify their proposal pricing.

## Research Strategy
Search the web for real pricing data. Focus on:
- Agency pricing guides and rate cards (India preferred, global as fallback)
- Industry reports on creative/design service costs
- Clutch, DesignRush, and agency review platform data
- Published case studies with known budgets
- Quora/Reddit threads discussing agency costs (lower quality but useful for ranges)

You have up to {max_searches} web searches. Use them strategically — one search per major category, plus follow-ups for thin results.

## Categories to Benchmark
{categories_section}

## Output Format (markdown)

# Market Benchmarks

For each service category:

## [Category Name]

| Tier | Price Range | Source |
|------|-------------|--------|
| Budget / Freelancer | ₹X — ₹Y | [source name, year] |
| Mid-tier Agency | ₹X — ₹Y | [source name, year] |
| Premium / Enterprise Agency | ₹X — ₹Y | [source name, year] |

**Data confidence**: High (3+ sources) / Medium (2 sources) / Low (1 source or estimates)
**Notes**: [any relevant context about pricing variations]

---

## Rules
- NEVER fabricate benchmark numbers. If you can't find real data, say "No published benchmark found — estimate from rate card needed."
- Always cite the source (publication name + year) for every number.
- Prefer recent data (2025-2026) over older sources.
- Prefer Indian pricing data for India-based proposals. Convert USD to INR at ₹84/$1 if only USD found.
- Include the source URL when available.
- Note when prices include or exclude GST."""


class BenchmarkAgent:
    def __init__(self):
        self._client = AnthropicClient()

    async def find_benchmarks(
        self,
        deliverables: list[dict],
        country: str = "India",
        template_queries: list[str] | None = None,
        template_categories: list[str] | None = None,
        max_searches: int = 8,
    ) -> str:
        """Search for pricing benchmarks using Claude's native web search. Returns markdown."""
        if not self._client.is_configured:
            return "# Market Benchmarks\n\n*AI not configured. Set ANTHROPIC_API_KEY to enable benchmarking.*"

        # Build categories section
        categories = set()
        for d in deliverables:
            cat = d.get("category", "")
            details = d.get("details", "")
            if cat:
                categories.add(f"{cat}: {details}" if details else cat)

        categories_section = "\n".join(f"- {c}" for c in categories) if categories else "- General design agency services"

        if template_queries:
            extra = "\n".join(f"- {q}" for q in template_queries)
            categories_section += f"\n\nAlso search for:\n{extra}"

        system = BENCHMARK_SYSTEM.format(
            max_searches=max_searches,
            categories_section=categories_section,
        )

        user_msg = f"Find pricing benchmarks for these design/creative agency services in {country}. Search the web for real published data."

        settings = get_settings()

        response = await self._client._client.messages.create(
            model=settings.ANTHROPIC_DEFAULT_MODEL,
            max_tokens=4096,
            system=system,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_searches,
            }],
            messages=[{"role": "user", "content": user_msg}],
        )

        text_parts = []
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text_parts.append(block.text)

        return "".join(text_parts) if text_parts else "# Market Benchmarks\n\nNo benchmark data found."

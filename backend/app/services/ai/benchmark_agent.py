from __future__ import annotations

from app.infrastructure.external.anthropic_client import AnthropicClient
from app.infrastructure.external.web_search_client import WebSearchClient

SYNTHESIS_PROMPT = """You are a market research assistant for a proposal copilot. Given web search results about pricing for specific service categories, extract structured benchmark data.

## Output format (markdown):

# Market Benchmarks

For each service category, provide:

## [Category Name]
| Tier | Price Range | Source |
|------|-------------|--------|
| Budget/Freelancer | ₹X - ₹Y | [source] |
| Mid-tier Agency | ₹X - ₹Y | [source] |
| Premium Agency | ₹X - ₹Y | [source] |

**Data points found**: [number]
**Confidence**: High / Medium / Low

---

## Rules:
- Only include data you actually found in search results. NEVER fabricate benchmark numbers.
- If no data found for a category, write: "No published benchmark found — estimate from rate card needed."
- Prefer Indian pricing data. Convert USD to INR at 1 USD = ₹84 if only USD sources found.
- Always cite the source (publication name + year).
- Prefer recent data (2025-2026) over older sources."""


class BenchmarkAgent:
    def __init__(self):
        self._search = WebSearchClient()
        self._llm = AnthropicClient()

    async def find_benchmarks(
        self,
        deliverables: list[dict],
        country: str = "India",
        template_queries: list[str] | None = None,
        template_categories: list[str] | None = None,
    ) -> str:
        """Search for pricing benchmarks per deliverable category. Returns markdown."""
        # Build search queries per deliverable category
        categories = set()
        for d in deliverables:
            cat = d.get("category", "")
            if cat:
                categories.add(cat)

        queries = template_queries or []
        if not queries:
            year = "2025 2026"
            for cat in categories:
                queries.append(f"{cat} cost {country} agency {year}")
                queries.append(f"{cat} pricing guide agency")

        # Replace placeholders
        queries = [
            q.replace("{country}", country)
             .replace("{year}", "2026")
             .replace("{service_type}", "design agency services")
            for q in queries
        ]

        # Cap at 10 queries to stay within reasonable search budget
        queries = queries[:10]

        # Run searches
        all_results = await self._search.search_multiple(queries, num_per_query=3)

        # Format for Claude
        search_context = self._format_results(all_results)
        category_list = ", ".join(categories) if categories else "general agency services"

        if not self._llm.is_configured:
            return f"# Market Benchmarks\n\n*AI not configured. Search results:*\n\n{search_context}"

        # Synthesize with Claude
        benchmarks = await self._llm.complete(
            system=SYNTHESIS_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Categories to benchmark: {category_list}\nCountry: {country}\n\nSearch results:\n\n{search_context}",
            }],
            max_tokens=3000,
            temperature=0.3,
        )
        return benchmarks

    def _format_results(self, results: dict[str, list]) -> str:
        parts = []
        for query, items in results.items():
            parts.append(f"### Query: {query}")
            for r in items:
                parts.append(f"- **{r.title}** ({r.url})\n  {r.snippet}")
            parts.append("")
        return "\n".join(parts)

from __future__ import annotations

from app.infrastructure.external.anthropic_client import AnthropicClient
from app.infrastructure.external.web_search_client import WebSearchClient

SYNTHESIS_PROMPT = """You are a research assistant for a proposal copilot. Given web search results about a client, synthesize them into a structured research report.

## Output format (markdown):

# Client Research: {client_name}

## Company Overview
- Founded: [year]
- Revenue: [amount]
- Employees: ~[number]
- Industry: [sector]
- Headquarters: [city]

## Recent Developments
- [bullet points from search results]

## Leadership
- CEO/MD: [name]
- Key contacts mentioned: [names and roles if found]

## Current Brand/Digital Presence
- [observations about their website, social presence, brand quality]

## Relevance to Our Proposal
- [2-3 observations that should inform our approach]

## Sources
- [list URLs used]

Only include information you actually found in the search results. Do not fabricate. If something was not found, omit that section rather than guessing."""


class ResearchAgent:
    def __init__(self):
        self._search = WebSearchClient()
        self._llm = AnthropicClient()

    async def research_client(
        self,
        client_name: str,
        industry: str | None = None,
        template_queries: list[str] | None = None,
    ) -> str:
        """Research the client using web search + Claude synthesis. Returns markdown."""
        # Build search queries
        queries = template_queries or []
        if not queries:
            year = "2025 2026"
            queries = [
                f"{client_name} company overview revenue",
                f"{client_name} recent news {year}",
                f"{client_name} CEO leadership",
                f"{client_name} awards recognition {year}",
            ]
            if industry:
                queries.append(f"{client_name} {industry} competitors")

        # Replace placeholders
        queries = [
            q.replace("{client}", client_name)
             .replace("{industry}", industry or "")
             .replace("{year}", "2026")
            for q in queries
        ]

        # Run searches
        all_results = await self._search.search_multiple(queries, num_per_query=3)

        # Format results for Claude
        search_context = self._format_results(all_results)

        if not self._llm.is_configured:
            return f"# Client Research: {client_name}\n\n*AI not configured. Search results:*\n\n{search_context}"

        # Synthesize with Claude
        research = await self._llm.complete(
            system=SYNTHESIS_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Client: {client_name}\nIndustry: {industry or 'Unknown'}\n\nSearch results:\n\n{search_context}",
            }],
            max_tokens=2048,
            temperature=0.3,
        )
        return research

    def _format_results(self, results: dict[str, list]) -> str:
        parts = []
        for query, items in results.items():
            parts.append(f"### Query: {query}")
            for r in items:
                parts.append(f"- **{r.title}** ({r.url})\n  {r.snippet}")
            parts.append("")
        return "\n".join(parts)

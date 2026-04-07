from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchClient:
    def __init__(self):
        settings = get_settings()
        self._api_key = settings.SERPER_API_KEY
        self._base_url = "https://google.serper.dev/search"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Run a web search via Serper API. Returns top results."""
        if not self.is_configured:
            return [SearchResult(
                title="Search not configured",
                url="",
                snippet=f"Set SERPER_API_KEY in .env to enable web search. Query was: {query}",
            )]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._base_url,
                json={"q": query, "num": num_results},
                headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("organic", [])[:num_results]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            ))
        return results

    async def search_multiple(self, queries: list[str], num_per_query: int = 3) -> dict[str, list[SearchResult]]:
        """Run multiple searches. Returns {query: [results]}."""
        results = {}
        for q in queries:
            try:
                results[q] = await self.search(q, num_per_query)
            except Exception:
                results[q] = []
        return results

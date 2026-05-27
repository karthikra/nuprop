"""Serper-backed search + LLM synthesis.

Replacement for Anthropic's hosted web_search tool which AWS Bedrock in
ap-northeast-1 doesn't expose (see ``docs/superpowers/specs/bedrock-web-search-fix.md``
Option 2, and HANDOFF § 5e).

Flow:
  1. Caller provides pre-computed search queries (from ``research_planner``
     or ``benchmarks_planner``).
  2. ``execute_search_plan`` runs each query via the Serper-backed
     ``WebSearchClient``, emitting one ``{type: "search", ...}`` event per
     query and one ``{type: "read", ...}`` event per result URL — same
     event shape ``process_stream`` used to emit, so the frontend
     ``research-activity-log`` component renders without modification.
  3. ``synthesize_research`` then issues a single non-streaming LLM call
     to digest all search hits into a markdown body with inline ``[N]``
     citation markers matching the numbered ``citations`` list.

Returns ``(body, citations, spans)`` where ``spans`` is always empty —
inline citation offsets would require the LLM to emit citation locations
in its stream (the Anthropic-hosted ``web_search`` tool's feature). With
our own search backend we settle for ``[N]`` markers + a numbered list,
which is what most academic-style research briefs use anyway.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from app.infrastructure.external.web_search_client import SearchResult, WebSearchClient
from app.services.llm import Tier, get_ai_service

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:  # noqa: BLE001
        return url


def _format_results_for_synthesis(results: list[SearchResult]) -> str:
    """Inline numbered search hits as the synthesis prompt's grounding section."""
    if not results:
        return ""
    lines: list[str] = []
    for i, r in enumerate(results, start=1):
        lines.append(f"[{i}] {r.title or _parse_domain(r.url)}")
        lines.append(f"    URL: {r.url}")
        lines.append(f"    {r.snippet}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _build_citations(results: list[SearchResult]) -> list[dict[str, Any]]:
    """Produce the ``{id, url, title, domain, cited_text}`` shape the
    ``research_findings`` card expects. ``cited_text`` is empty since we
    don't have LLM-emitted citation spans — the inline ``[N]`` markers in
    the body do the same job."""
    return [
        {
            "id": i,
            "url": r.url,
            "title": r.title or _parse_domain(r.url),
            "domain": _parse_domain(r.url),
            "cited_text": "",
        }
        for i, r in enumerate(results, start=1)
        if r.url  # skip placeholder rows from misconfigured WebSearchClient
    ]


async def execute_search_plan(
    *,
    queries: list[str],
    on_event: EventCallback,
    web_search_client: WebSearchClient | None = None,
    per_query_results: int = 5,
) -> list[SearchResult]:
    """Run each query via Serper, emit ``search`` + ``read`` activity events.

    Returns the deduplicated-by-URL flat list of all results across queries
    (preserves the first occurrence of each URL).
    """
    client = web_search_client or WebSearchClient()
    seen_urls: set[str] = set()
    all_results: list[SearchResult] = []
    for query in queries:
        if not query:
            continue
        await on_event({"type": "search", "query": query, "ts": _now_iso()})
        results = await client.search(query, num_results=per_query_results)
        for r in results:
            if not r.url or r.url in seen_urls:
                continue
            seen_urls.add(r.url)
            await on_event({
                "type": "read",
                "url": r.url,
                "title": r.title or _parse_domain(r.url),
                "ts": _now_iso(),
            })
            all_results.append(r)
    return all_results


async def synthesize_research(
    *,
    queries: list[str],
    system_prompt: str,
    user_message: str,
    on_event: EventCallback,
    max_tokens: int = 4096,
    tier: Tier = Tier.BALANCED,
    web_search_client: WebSearchClient | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """End-to-end: run Serper searches, synthesize a cited markdown brief.

    Returns ``(body, citations, spans)``. ``spans`` is always empty (see
    module docstring).
    """
    results = await execute_search_plan(
        queries=queries,
        on_event=on_event,
        web_search_client=web_search_client,
    )

    await on_event({
        "type": "note",
        "text": (
            f"Synthesizing findings from {len(results)} search results..."
            if results
            else "No search results returned — synthesizing from training-data knowledge only."
        ),
        "ts": _now_iso(),
    })

    if results:
        search_context = _format_results_for_synthesis(results)
        augmented_user_message = (
            f"{user_message}\n\n"
            f"## Search results to draw from\n\n{search_context}\n\n"
            f"Synthesize these into a comprehensive research brief. Cite sources "
            f"inline using [N] markers matching the result numbers above. Do not "
            f"invent facts that aren't present in the search results."
        )
    else:
        augmented_user_message = (
            f"{user_message}\n\n"
            f"NOTE: Web search returned no live results. Write the brief based on "
            f"what you know about this from your training data, and flag any facts "
            f"you're uncertain about. Do not fabricate citations."
        )

    ai = get_ai_service()
    result = await ai.complete(
        prompt=augmented_user_message,
        system=system_prompt,
        tier=tier,
        max_tokens=max_tokens,
    )
    citations = _build_citations(results)
    spans: list[dict[str, Any]] = []
    return result.text, citations, spans

"""Unit tests for the Serper-backed search + synthesis helper.

Replaces the broken Anthropic-hosted web_search path (Bedrock 400). Tests
mock both the WebSearchClient (Serper) and the AIService so they're pure
in-memory and don't depend on any infra.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.external.web_search_client import SearchResult
from app.services.ai import web_search_loop
from app.services.llm import LLMResult, Tier


@pytest.fixture
def _fake_search_client():
    """Returns a WebSearchClient whose .search returns canned results per query."""
    client = MagicMock()
    canned = {
        "acme rebrand": [
            SearchResult(title="Acme Q3 results", url="https://example.com/acme-q3", snippet="rev up 12%"),
            SearchResult(title="Acme press release", url="https://example.com/acme-pr", snippet="rebranding push"),
        ],
        "acme industry": [
            SearchResult(title="Industry overview", url="https://example.com/industry", snippet="market is hot"),
        ],
    }

    async def _search(query, num_results=5):  # noqa: ARG001
        return canned.get(query, [])

    client.search = AsyncMock(side_effect=_search)
    return client


@pytest.fixture
def _fake_ai(monkeypatch):
    """Patch get_ai_service to return an AI mock that yields a fixed LLMResult."""
    mock = MagicMock()
    mock.complete = AsyncMock(return_value=LLMResult(
        text="# Acme research\n\nAcme had strong Q3 [1]. Rebranding is underway [2].",
        input_tokens=100,
        output_tokens=42,
    ))
    monkeypatch.setattr(web_search_loop, "get_ai_service", lambda: mock)
    return mock


async def test_execute_search_plan_emits_search_and_read_events(_fake_search_client):
    events: list[dict] = []

    async def collect(e):
        events.append(e)

    results = await web_search_loop.execute_search_plan(
        queries=["acme rebrand", "acme industry"],
        on_event=collect,
        web_search_client=_fake_search_client,
    )

    # Two queries -> two search events.
    search_events = [e for e in events if e["type"] == "search"]
    assert [e["query"] for e in search_events] == ["acme rebrand", "acme industry"]

    # Three unique URLs across both queries -> three read events.
    read_events = [e for e in events if e["type"] == "read"]
    assert len(read_events) == 3
    assert {e["url"] for e in read_events} == {
        "https://example.com/acme-q3",
        "https://example.com/acme-pr",
        "https://example.com/industry",
    }
    # Read events carry a title.
    for r in read_events:
        assert r["title"]

    # Returned results match the read order (deduped, ordered).
    assert [r.url for r in results] == [
        "https://example.com/acme-q3",
        "https://example.com/acme-pr",
        "https://example.com/industry",
    ]


async def test_execute_search_plan_skips_empty_queries(_fake_search_client):
    events: list[dict] = []

    async def collect(e):
        events.append(e)

    await web_search_loop.execute_search_plan(
        queries=["", "acme rebrand", ""],
        on_event=collect,
        web_search_client=_fake_search_client,
    )

    # Only the non-empty query produces a search event.
    assert sum(1 for e in events if e["type"] == "search") == 1


async def test_execute_search_plan_deduplicates_repeated_urls(monkeypatch):
    client = MagicMock()
    same_result = SearchResult(title="Same", url="https://example.com/same", snippet="x")

    async def _search(query, num_results=5):  # noqa: ARG001
        return [same_result]

    client.search = AsyncMock(side_effect=_search)

    events: list[dict] = []
    results = await web_search_loop.execute_search_plan(
        queries=["q1", "q2", "q3"],
        on_event=lambda e: _append_async(events, e),
        web_search_client=client,
    )

    # Three searches but only one unique URL across them.
    assert len([e for e in events if e["type"] == "search"]) == 3
    assert len([e for e in events if e["type"] == "read"]) == 1
    assert len(results) == 1


async def _append_async(target: list, item):
    """Helper used in the dedupe test where we want an async lambda."""
    target.append(item)


async def test_synthesize_research_passes_results_to_ai_and_returns_body(
    _fake_search_client, _fake_ai,
):
    events: list[dict] = []

    async def collect(e):
        events.append(e)

    body, citations, spans = await web_search_loop.synthesize_research(
        queries=["acme rebrand", "acme industry"],
        system_prompt="You are a researcher.",
        user_message="Research Acme.",
        on_event=collect,
        web_search_client=_fake_search_client,
    )

    # Body comes from the AI mock.
    assert body.startswith("# Acme research")

    # Citations are built from search results, numbered 1..N.
    assert [c["id"] for c in citations] == [1, 2, 3]
    assert [c["url"] for c in citations] == [
        "https://example.com/acme-q3",
        "https://example.com/acme-pr",
        "https://example.com/industry",
    ]
    assert all(c["domain"] == "example.com" for c in citations)
    assert all(c["cited_text"] == "" for c in citations)

    # Spans intentionally empty (no streamed citation positions).
    assert spans == []

    # A trailing 'note' event is emitted before synthesis fires.
    note_events = [e for e in events if e["type"] == "note"]
    assert len(note_events) == 1
    assert "3 search results" in note_events[0]["text"]

    # The AI was called with the augmented prompt containing the search context.
    call = _fake_ai.complete.await_args
    prompt = call.kwargs["prompt"]
    assert "Acme Q3 results" in prompt
    assert "[1]" in prompt
    assert "[3]" in prompt
    assert call.kwargs["tier"] == Tier.BALANCED
    assert call.kwargs["system"] == "You are a researcher."


async def test_synthesize_research_empty_results_falls_back_to_llm_only(monkeypatch, _fake_ai):
    """If Serper returns nothing, we still produce a body — flagged as LLM-only."""
    client = MagicMock()
    client.search = AsyncMock(return_value=[])

    events: list[dict] = []

    async def collect(e):
        events.append(e)

    body, citations, _ = await web_search_loop.synthesize_research(
        queries=["q1", "q2"],
        system_prompt="sys",
        user_message="user",
        on_event=collect,
        web_search_client=client,
    )

    assert body  # AI still ran
    assert citations == []
    # The 'note' event explicitly flags the no-results state.
    note = next(e for e in events if e["type"] == "note")
    assert "No search results" in note["text"]
    # The augmented prompt warns the LLM not to fabricate.
    prompt = _fake_ai.complete.await_args.kwargs["prompt"]
    assert "do not fabricate" in prompt.lower() or "uncertain" in prompt.lower()


async def test_synthesize_research_skips_results_with_blank_url(monkeypatch, _fake_ai):
    client = MagicMock()
    client.search = AsyncMock(return_value=[
        SearchResult(title="Real", url="https://example.com/real", snippet="x"),
        SearchResult(title="Search not configured", url="", snippet="placeholder"),
    ])

    events: list[dict] = []

    async def collect(e):
        events.append(e)

    body, citations, _ = await web_search_loop.synthesize_research(
        queries=["q"],
        system_prompt="sys",
        user_message="user",
        on_event=collect,
        web_search_client=client,
    )

    # Only the real result becomes a citation; the empty-URL row is skipped.
    assert len(citations) == 1
    assert citations[0]["url"] == "https://example.com/real"
    assert body

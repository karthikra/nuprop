"""Unit tests for the hosted-web-search streaming helper.

``synthesize_research`` routes to Anthropic's direct API (not Bedrock)
because Bedrock in ap-northeast-1 doesn't expose the hosted web_search
tool. Tests patch ``AsyncAnthropic`` + ``process_stream`` so no real
network call ever runs.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai import web_search_loop
from app.services.llm import Tier


class _FakeStream:
    """Stands in for the async-context-manager returned by ``messages.stream``."""

    def __init__(self):
        self.kwargs = None

    async def __aenter__(self):
        return self  # process_stream is mocked, so the stream body isn't iterated

    async def __aexit__(self, *args):
        return None


def _install_fake_anthropic(monkeypatch, *, capture: dict):
    """Patch ``anthropic.AsyncAnthropic`` so synthesize_research doesn't hit
    the real API. Returned dict captures construction + stream call kwargs."""
    fake_stream = _FakeStream()

    def _stream(**kwargs):
        capture["stream_kwargs"] = kwargs
        return fake_stream

    fake_client = MagicMock()
    fake_client.messages.stream = _stream

    def _AsyncAnthropic(**kwargs):  # noqa: N802 — mirror real class name
        capture["client_kwargs"] = kwargs
        return fake_client

    fake_anthropic_module = SimpleNamespace(AsyncAnthropic=_AsyncAnthropic)
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_anthropic_module)
    return fake_client


def _install_fake_process_stream(monkeypatch, *, body: str = "research body", citations=None, spans=None):
    """Patch ``process_stream`` so we control the (body, citations, spans) tuple
    that synthesize_research returns, AND verify the on_event callback fires."""
    citations = citations or []
    spans = spans or []

    async def _fake(stream, *, on_event):
        # Mimic the real process_stream's event emission so callers see activity.
        await on_event({"type": "search", "query": "hosted-search-query"})
        await on_event({"type": "read", "url": "https://hosted.example/a", "title": "A"})
        return body, citations, spans

    monkeypatch.setattr(web_search_loop, "process_stream", _fake)


async def test_synthesize_research_uses_direct_api_with_hosted_tool(monkeypatch):
    """The streaming call must (a) instantiate AsyncAnthropic with the direct
    API key, (b) include the web_search_20250305 tool, (c) use a bare model
    ID (not a Bedrock inference-profile ID)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # cleared then set via settings
    from app.core.config import Settings

    # Patch get_settings to return a Settings with our key.
    fake_settings = Settings(ANTHROPIC_API_KEY="sk-direct-test-key")
    monkeypatch.setattr(web_search_loop, "get_settings", lambda: fake_settings)

    capture: dict = {}
    _install_fake_anthropic(monkeypatch, capture=capture)
    _install_fake_process_stream(monkeypatch)

    events: list[dict] = []

    async def on_event(e):
        events.append(e)

    body, citations, spans = await web_search_loop.synthesize_research(
        queries=["ignored-by-hosted-search"],
        system_prompt="You are a researcher.",
        user_message="Research Acme.",
        on_event=on_event,
    )

    assert body == "research body"
    assert spans == []
    assert citations == []

    # AsyncAnthropic constructed with the right API key.
    assert capture["client_kwargs"]["api_key"] == "sk-direct-test-key"

    # Stream invoked with the hosted web_search tool + direct-API model ID.
    s = capture["stream_kwargs"]
    assert s["model"] == "claude-sonnet-4-6"  # bare ID, not "global.anthropic.*"
    assert s["system"] == "You are a researcher."
    assert s["messages"] == [{"role": "user", "content": "Research Acme."}]
    assert s["tools"] == [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 10,
    }]

    # Events flowed through process_stream to our callback.
    assert any(e["type"] == "search" for e in events)
    assert any(e["type"] == "read" for e in events)


async def test_synthesize_research_uses_heavy_tier_model_id_when_requested(monkeypatch):
    """Tier.HEAVY must resolve to claude-opus-4-7 on the direct API."""
    from app.core.config import Settings
    fake_settings = Settings(ANTHROPIC_API_KEY="sk-test")
    monkeypatch.setattr(web_search_loop, "get_settings", lambda: fake_settings)

    capture: dict = {}
    _install_fake_anthropic(monkeypatch, capture=capture)
    _install_fake_process_stream(monkeypatch)

    await web_search_loop.synthesize_research(
        queries=[],
        system_prompt="s",
        user_message="u",
        on_event=lambda e: _noop(e),
        tier=Tier.HEAVY,
    )

    assert capture["stream_kwargs"]["model"] == "claude-opus-4-7"


async def test_synthesize_research_raises_without_api_key(monkeypatch):
    """Without ANTHROPIC_API_KEY the call should fail fast with a clear error,
    not silently fall through to garbage output."""
    from app.core.config import Settings
    fake_settings = Settings(ANTHROPIC_API_KEY="")
    monkeypatch.setattr(web_search_loop, "get_settings", lambda: fake_settings)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await web_search_loop.synthesize_research(
            queries=[],
            system_prompt="s",
            user_message="u",
            on_event=lambda e: _noop(e),
        )


async def test_synthesize_research_respects_max_searches_override(monkeypatch):
    """``max_searches`` propagates to the tool's max_uses field."""
    from app.core.config import Settings
    fake_settings = Settings(ANTHROPIC_API_KEY="sk-test")
    monkeypatch.setattr(web_search_loop, "get_settings", lambda: fake_settings)

    capture: dict = {}
    _install_fake_anthropic(monkeypatch, capture=capture)
    _install_fake_process_stream(monkeypatch)

    await web_search_loop.synthesize_research(
        queries=[],
        system_prompt="s",
        user_message="u",
        on_event=lambda e: _noop(e),
        max_searches=3,
    )

    assert capture["stream_kwargs"]["tools"][0]["max_uses"] == 3


async def _noop(_e):
    return None

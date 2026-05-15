"""Surface-area regression tests for the AnthropicClient Bedrock facade.

The facade is the public interface AI agents (ResearchAgent, BenchmarkAgent,
BriefAnalyzer, CostModelBuilder, NarrativeGenerator, EmailClassifier,
ContextService) program against. If any method or property goes missing the
agents will crash at runtime with ``AttributeError`` — which is exactly what
happened during the Bedrock migration when the internal SDK-client field was
renamed from ``_client`` to ``_ai``: agents that reached in via
``self._client._client.messages.create(...)`` for native web-search tool use
silently broke, the suite stayed green (because per-agent tests mock the agent
methods themselves), and the failure only surfaced live at the
``run_research`` phase.

These tests lock in the public surface so renames or removals fail fast.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.external.anthropic_client import AnthropicClient


def test_facade_exposes_the_methods_agents_depend_on():
    """If any of these go away, an AI agent breaks. Lock them in."""
    expected = {"complete", "complete_json", "stream", "messages_create", "is_configured"}
    for name in expected:
        assert hasattr(AnthropicClient, name), (
            f"AnthropicClient.{name} missing — an AI agent will crash with AttributeError"
        )


async def test_messages_create_delegates_to_AIService(monkeypatch):
    """ResearchAgent and BenchmarkAgent call ``self._client.messages_create(**kwargs)``
    for native web-search tool use. The facade must proxy through to AIService
    with the kwargs untouched."""
    fake_ai = MagicMock()
    fake_ai.messages_create = AsyncMock(return_value="sentinel")
    monkeypatch.setattr(
        "app.infrastructure.external.anthropic_client.get_ai_service",
        lambda: fake_ai,
    )

    client = AnthropicClient()
    result = await client.messages_create(
        model="m", max_tokens=10, system="s",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
    )

    fake_ai.messages_create.assert_awaited_once()
    fwd = fake_ai.messages_create.await_args.kwargs
    assert fwd["model"] == "m"
    assert fwd["max_tokens"] == 10
    assert fwd["system"] == "s"
    assert fwd["messages"] == [{"role": "user", "content": "hi"}]
    assert fwd["tools"][0]["type"] == "web_search_20250305"
    assert result == "sentinel"

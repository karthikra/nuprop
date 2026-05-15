"""Backward-compatible facade over ``app.services.llm.AIService``.

Existing AI agents (BriefAnalyzer, ResearchAgent, BenchmarkAgent, CostModelBuilder,
NarrativeGenerator, EmailClassifier, ContextService) call ``AnthropicClient()``
and use ``.complete()`` / ``.complete_json()`` / ``.stream()`` / ``.is_configured``.

This module preserves that surface so the agents don't need code changes, but
internally every call goes through ``AIService`` → ``AsyncAnthropicBedrock``.
Direct ``anthropic.AsyncAnthropic`` use is gone — all inference routes through
AWS Bedrock per the project's CLAUDE.md policy.

The class-level method names are what ``tests/conftest.py:_no_network`` patches,
so this surface must stay stable for the test guard to keep working.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from app.core.config import get_settings
from app.services.llm import AIService, Tier, get_ai_service


def _tier_for_model(model_id: str | None) -> Tier | None:
    """Resolve a Bedrock model ID to its tier — supports legacy callers that
    pass ``model=settings.ANTHROPIC_OPUS_MODEL`` rather than a Tier."""
    if not model_id:
        return None
    settings = get_settings()
    if model_id == settings.ANTHROPIC_OPUS_MODEL:
        return Tier.HEAVY
    if model_id == settings.ANTHROPIC_HAIKU_MODEL:
        return Tier.FAST
    if model_id == settings.ANTHROPIC_DEFAULT_MODEL:
        return Tier.BALANCED
    return None  # unknown → let AIService use its default tier


class AnthropicClient:
    """Facade over :class:`AIService`. New code should use ``AIService`` directly;
    this class exists so the existing agents (and the no-network test guard) work
    unchanged after the Bedrock migration."""

    def __init__(self) -> None:
        self._ai: AIService = get_ai_service()
        settings = get_settings()
        self._default_model = settings.ANTHROPIC_DEFAULT_MODEL
        self._opus_model = settings.ANTHROPIC_OPUS_MODEL

    async def complete(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        result = await self._ai.complete(
            prompt=messages,
            tier=_tier_for_model(model),
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return result.text

    async def complete_json(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        return await self._ai.complete_json(
            prompt=messages,
            tier=_tier_for_model(model),
            system=system,
            max_tokens=max_tokens,
        )

    async def stream(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        async for chunk in self._ai.stream(
            prompt=messages,
            tier=_tier_for_model(model),
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield chunk

    @property
    def is_configured(self) -> bool:
        """Always True under Bedrock — auth comes from the AWS SDK credential
        chain at call time, not from an in-process API key. Callers that gate on
        ``is_configured`` no longer have a config check to make; Bedrock will
        raise ``AccessDeniedException`` at the call site if creds are missing.
        Tests still monkeypatch this to False to force fallback paths."""
        return True

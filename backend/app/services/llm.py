"""LLM service — single point of access to Claude via AWS Bedrock.

Every Claude call in NUPROP routes through ``AIService``. Direct ``anthropic``
SDK use anywhere else is a bug — see the project's CLAUDE.md policy:
*"always route through AWS Bedrock using AsyncAnthropicBedrock; never use the
direct Anthropic API or ANTHROPIC_API_KEY"*.

Auth comes from the AWS SDK credential chain (profile, env vars, instance role).
Region defaults to ``ap-northeast-1`` (Tokyo) for lowest latency from Bangalore.

The service is tier-aware: HEAVY (Opus 4.7) drops the ``temperature`` /
``top_p`` / ``top_k`` knobs because Opus 4.7 rejects them with a 400; BALANCED
(Sonnet 4.6) and FAST (Haiku 4.5) still accept them.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from enum import Enum
from functools import lru_cache
from typing import Any

from anthropic import AsyncAnthropicBedrock
from pydantic import BaseModel

from app.core.config import get_settings


# Hard ceiling on a single Bedrock call. Pipeline phases run as independent
# ARQ jobs; without this a hung call stalls the whole phase indefinitely.
LLM_TIMEOUT_SECONDS = 120.0


class Tier(str, Enum):
    HEAVY = "heavy"          # Opus 4.7 — complex reasoning, agentic loops
    BALANCED = "balanced"    # Sonnet 4.6 — production default
    FAST = "fast"            # Haiku 4.5 — high-volume batch / classification


def _tier_models(settings) -> dict[Tier, str]:
    return {
        Tier.HEAVY: settings.ANTHROPIC_OPUS_MODEL,
        Tier.BALANCED: settings.ANTHROPIC_DEFAULT_MODEL,
        Tier.FAST: settings.ANTHROPIC_HAIKU_MODEL,
    }


# Models that 400 on ``temperature`` / ``top_p`` / ``top_k`` — strip before send.
_NO_SAMPLING_PARAMS: set[Tier] = {Tier.HEAVY}


class LLMResult(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int


class AIService:
    """Bedrock-routed Claude client with tier-aware param handling.

    Construct once; reuse across requests. Use ``get_ai_service()`` for the
    lru_cached singleton.
    """

    def __init__(self, aws_region: str | None = None, aws_profile: str | None = None):
        settings = get_settings()
        kwargs: dict[str, Any] = {
            "aws_region": aws_region or settings.AWS_REGION,
            "timeout": LLM_TIMEOUT_SECONDS,
        }
        # Only pass profile if explicitly set — otherwise let the SDK credential
        # chain (env vars, instance role) take over.
        profile = aws_profile if aws_profile is not None else settings.AWS_PROFILE
        if profile:
            kwargs["aws_profile"] = profile
        self.client = AsyncAnthropicBedrock(**kwargs)
        self._models = _tier_models(settings)
        self.default_tier = Tier.BALANCED

    # ── public API ─────────────────────────────────────────────────────────
    async def complete(
        self,
        prompt: str | list[dict],
        *,
        tier: Tier | None = None,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> LLMResult:
        """Single-shot completion. ``prompt`` may be a string or a pre-built
        list of role/content messages."""
        messages = (
            [{"role": "user", "content": prompt}]
            if isinstance(prompt, str)
            else prompt
        )
        kwargs = self._build_kwargs(
            tier=tier or self.default_tier,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            temperature=temperature,
        )
        response = await self.client.messages.create(**kwargs)
        return LLMResult(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def complete_json(
        self,
        prompt: str | list[dict],
        *,
        tier: Tier | None = None,
        system: str = "",
        max_tokens: int = 1024,
    ) -> Any:
        """Always returns parsed JSON. Raises ``json.JSONDecodeError`` on failure."""
        sys_with_json = (system + "\n\nReturn ONLY valid JSON. No markdown, no explanation.").strip()
        result = await self.complete(
            prompt, tier=tier, system=sys_with_json, max_tokens=max_tokens
        )
        text = result.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    async def stream(
        self,
        prompt: str | list[dict],
        *,
        tier: Tier | None = None,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """Yields text chunks as they arrive."""
        messages = (
            [{"role": "user", "content": prompt}]
            if isinstance(prompt, str)
            else prompt
        )
        kwargs = self._build_kwargs(
            tier=tier or self.default_tier,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            temperature=temperature,
        )
        async with self.client.messages.stream(**kwargs) as s:
            async for chunk in s.text_stream:
                yield chunk

    async def messages_create(self, **kwargs: Any) -> Any:
        """Escape hatch for tool-use loops, vision payloads, prompt caching —
        anything that needs the raw ``messages.create`` surface. Caller is
        responsible for picking a tier-appropriate parameter set; consider
        ``_build_kwargs`` first."""
        return await self.client.messages.create(**kwargs)

    # ── kwargs builder — tier-aware ────────────────────────────────────────
    def _build_kwargs(
        self,
        tier: Tier,
        max_tokens: int,
        system: str | list,
        messages: list[dict],
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._models[tier],
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tier not in _NO_SAMPLING_PARAMS:
            if temperature is not None:
                kwargs["temperature"] = temperature
            if top_p is not None:
                kwargs["top_p"] = top_p
            if top_k is not None:
                kwargs["top_k"] = top_k
        return kwargs

    def model_for(self, tier: Tier | None = None) -> str:
        """Resolve a tier to its Bedrock model ID."""
        return self._models[tier or self.default_tier]


@lru_cache(maxsize=1)
def get_ai_service() -> AIService:
    """Process-wide cached singleton."""
    return AIService()

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import anthropic

from app.core.config import get_settings


class AnthropicClient:
    def __init__(self):
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
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
        response = await self._client.messages.create(
            model=model or self._default_model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.content[0].text

    async def complete_json(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Call Claude expecting a JSON response. Parses the output."""
        text = await self.complete(
            system=system + "\n\nRespond ONLY with valid JSON. No markdown, no explanation.",
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        # Strip markdown code fence if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        return json.loads(text)

    async def stream(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Yields text chunks as they arrive from the API."""
        async with self._client.messages.stream(
            model=model or self._default_model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    @property
    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.ANTHROPIC_API_KEY)

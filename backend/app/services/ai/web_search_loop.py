"""Streaming research via Anthropic's hosted web_search tool.

Routes around AWS Bedrock for this one call: Bedrock in ap-northeast-1
doesn't expose ``web_search_20250305`` (Anthropic's server-side hosted
tool — see ``docs/superpowers/specs/bedrock-web-search-fix.md`` Option 1
and HANDOFF § 5e). We instantiate ``AsyncAnthropic`` with the direct API
key for this one call site; everything else in the pipeline stays on
Bedrock per the CLAUDE.md global policy.

The hosted tool runs an agentic search loop on Anthropic's infrastructure:
the model emits ``tool_use`` blocks with queries, Anthropic executes them,
reads the results, decides whether to do follow-up searches, and emits a
final ``text`` block with inline ``citations`` referencing the search
results it consulted. ``process_stream`` (existing) turns that stream into
``(body, citations, spans)`` for the findings card.

Cost: ~$0.20-0.40 per research run (Anthropic API tokens + $0.01/search ×
~5-10 searches). See HANDOFF § 5e for the per-scale breakdown.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.core.config import get_settings
from app.services.llm import Tier
from app.services.research_streaming import process_stream

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]

# Direct-API model IDs. These differ from the Bedrock inference-profile IDs
# in ANTHROPIC_DEFAULT_MODEL / ANTHROPIC_OPUS_MODEL etc. — Anthropic's direct
# API uses bare model strings like "claude-sonnet-4-6", not the global.*
# inference-profile prefix.
_DIRECT_MODEL_IDS: dict[Tier, str] = {
    Tier.HEAVY: "claude-opus-4-7",
    Tier.BALANCED: "claude-sonnet-4-6",
    Tier.FAST: "claude-haiku-4-5-20251001",
}


async def synthesize_research(
    *,
    queries: list[str],
    system_prompt: str,
    user_message: str,
    on_event: EventCallback,
    max_tokens: int = 4096,
    tier: Tier = Tier.BALANCED,
    max_searches: int = 10,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Run an agentic research call via Anthropic's hosted web_search.

    ``queries`` is accepted for API compatibility with the prior Serper
    implementation but is ignored — Anthropic's hosted tool decides which
    searches to issue based on the system + user messages. Pass a non-empty
    list anyway so the planner's chat-visible plan stays consistent with
    what the model is being asked to do.

    Raises ``RuntimeError`` if ``ANTHROPIC_API_KEY`` isn't configured.
    """
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not configured — hosted web_search requires the "
            "direct Anthropic API (Bedrock doesn't proxy this tool). Set the "
            "secret via `fly secrets set -a nuprop ANTHROPIC_API_KEY=\"...\"`."
        )

    # Lazy import so the test suite (which monkeypatches synthesize_research)
    # never has to pay the anthropic-client cost.
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    model = _DIRECT_MODEL_IDS[tier]
    tools = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": max_searches,
    }]

    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        tools=tools,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        body, citations, spans = await process_stream(stream, on_event=on_event)

    return body, citations, spans

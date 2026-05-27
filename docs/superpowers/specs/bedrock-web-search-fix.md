# Web search via Bedrock — diagnosis & fix

## Problem
Calling Claude on **Amazon Bedrock** (`ap-northeast-1`) with the web search tool returns:

```
400 — web_search is not a valid tag
```

## Root cause
`web_search_20250305` is one of Anthropic's **hosted (server-side) tools** — Anthropic
executes the search on their own infrastructure and returns the results inside the
response. **Bedrock only serves the model weights; it does not host that search backend**,
so the tool `type` is unknown to it.

This is **not** regional or model-specific:
- Same on every Bedrock region, and on Vertex AI.
- Switching Sonnet 4.6 ↔ Opus 4.7 makes no difference.

Bedrock's accepted tool `type` values are all **client-side**:
`bash`, `custom`, `memory`, `text_editor`, `tool_search`.
There is no `web_search` / `web_fetch` / `code_execution` of any version.

---

## Fix — Option 1 (recommended): route hosted-search calls to the first-party API
Keep Bedrock for normal calls; send only the calls that need hosted web search to
`AsyncAnthropic`. A single call site picks the provider based on the requested tools.

```python
import os
import anthropic

_DIRECT  = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_BEDROCK = anthropic.AsyncAnthropicBedrock(aws_region="ap-northeast-1")

# Anthropic hosted tools that Bedrock cannot execute.
_SERVER_SIDE_PREFIXES = ("web_search", "web_fetch", "code_execution")

# logical name -> (direct model id, bedrock inference-profile id)
# NB: confirm the bedrock ids via `aws bedrock list-inference-profiles`.
_MODELS = {
    "sonnet": ("claude-sonnet-4-6", "global.anthropic.claude-sonnet-4-6"),
    "opus":   ("claude-opus-4-7",   "global.anthropic.claude-opus-4-7"),
}

def _needs_direct(tools) -> bool:
    return any(t.get("type", "").startswith(_SERVER_SIDE_PREFIXES) for t in (tools or []))

async def create_message(*, model: str, tools=None, **kwargs):
    """Pick Bedrock vs first-party API based on whether a hosted tool is requested."""
    use_direct = _needs_direct(tools)
    client = _DIRECT if use_direct else _BEDROCK
    direct_id, bedrock_id = _MODELS[model]
    return await client.messages.create(
        model=direct_id if use_direct else bedrock_id,
        tools=tools,
        **kwargs,
    )
```

Usage stays uniform:

```python
resp = await create_message(
    model="sonnet",
    max_tokens=1500,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],  # -> routed to direct
    messages=[...],
)
```

---

## Fix — Option 2: BYO search as a custom tool (stay 100% on Bedrock)
`custom` is accepted, so define your own `web_search` tool, run the query yourself against
a search provider (Tavily / Exa / Brave Search API / Serper), and return results as a
`tool_result` in the agentic loop.

```python
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "Search the web for current information.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

async def run_with_search(client, model, messages):
    while True:
        resp = await client.messages.create(
            model=model, max_tokens=1500,
            tools=[WEB_SEARCH_TOOL], messages=messages,
        )
        if resp.stop_reason != "tool_use":
            return resp
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use" and block.name == "web_search":
                hits = await my_search_provider(block.input["query"])  # Tavily/Exa/etc.
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": format_hits(hits),
                })
        messages.append({"role": "user", "content": results})
```

Trade-off: you now manage a search vendor and format your own results, but everything
stays on Bedrock and you control the source.

---

## Decision
Use **Option 1** unless data residency or procurement pins everything to Bedrock.
Cost of Option 1: a second credential path + model-id mapping. Option 2 adds a search
vendor + result formatting.

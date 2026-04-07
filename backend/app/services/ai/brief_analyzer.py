from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from app.infrastructure.external.anthropic_client import AnthropicClient

SYSTEM_PROMPT = """You are NUPROP, an AI proposal copilot for design and professional services agencies.

You are in the BRIEF INTAKE phase. Your job is to understand what the client needs by gathering information conversationally. Ask questions one at a time — never dump all questions at once.

## Information to gather:
1. **Client**: Name, what they do, industry, approximate size
2. **Project**: What they need — specific deliverables, not vague descriptions
3. **Duration**: One-time project or ongoing engagement? Timeline?
4. **Budget**: Any budget signals or constraints mentioned?
5. **Competition**: Who else might be pitching? What's the agency's angle?
6. **Relationship**: Cold pitch, warm intro, or existing client? Who's the decision-maker?

## Rules:
- Ask ONE question at a time. Be conversational, not interrogative.
- If the user provides a lot of information upfront, extract what you can and only ask about gaps.
- When you have enough information (at minimum: client name, project type, and 2+ deliverables), you can complete the brief.
- When the brief is complete, respond with a JSON block wrapped in ```json``` fences containing the structured brief, followed by a summary asking the user to confirm.

## Brief JSON format:
```json
{
  "brief_complete": true,
  "brief": {
    "client": {
      "name": "",
      "industry": "",
      "size": "",
      "contacts": []
    },
    "project": {
      "type": "",
      "deliverables": [
        {"category": "", "details": "", "quantity": 1}
      ],
      "timeline": "",
      "budget_signal": ""
    },
    "context": {
      "relationship": "cold_pitch | warm_intro | existing_client",
      "competition": "",
      "urgency": "low | medium | high",
      "decision_maker": ""
    }
  }
}
```

If you don't have enough information yet, do NOT output the JSON. Just ask your next question naturally.

Remember: you are a senior business development lead having a natural conversation, not a form-filling bot."""


@dataclass
class BriefAnalysisResult:
    response_text: str
    brief_complete: bool = False
    brief_data: dict = field(default_factory=dict)


class BriefAnalyzer:
    def __init__(self):
        self._client = AnthropicClient()

    async def analyze(
        self,
        chat_history: list[dict],
        current_brief: dict,
    ) -> BriefAnalysisResult:
        """Process chat history and return the AI's response + optional completed brief."""
        messages = self._build_messages(chat_history, current_brief)
        response_text = await self._client.complete(
            system=SYSTEM_PROMPT,
            messages=messages,
            max_tokens=2048,
            temperature=0.7,
        )
        return self._parse_response(response_text)

    async def stream_analyze(
        self,
        chat_history: list[dict],
        current_brief: dict,
    ) -> AsyncGenerator[str, None]:
        """Stream the AI response token by token."""
        messages = self._build_messages(chat_history, current_brief)
        async for chunk in self._client.stream(
            system=SYSTEM_PROMPT,
            messages=messages,
            max_tokens=2048,
            temperature=0.7,
        ):
            yield chunk

    def _build_messages(self, chat_history: list[dict], current_brief: dict) -> list[dict]:
        """Convert chat history to Anthropic message format."""
        messages = []

        if current_brief:
            messages.append({
                "role": "user",
                "content": f"[SYSTEM CONTEXT — not a user message] Current brief state: {json.dumps(current_brief)}"
            })
            messages.append({
                "role": "assistant",
                "content": "Understood, I have the current brief context. I'll continue the conversation."
            })

        for msg in chat_history:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})

        return messages

    def _parse_response(self, text: str) -> BriefAnalysisResult:
        """Check if the response contains a completed brief JSON."""
        brief_complete = False
        brief_data = {}

        if "```json" in text and '"brief_complete": true' in text:
            try:
                json_start = text.index("```json") + 7
                json_end = text.index("```", json_start)
                json_str = text[json_start:json_end].strip()
                parsed = json.loads(json_str)
                if parsed.get("brief_complete"):
                    brief_complete = True
                    brief_data = parsed.get("brief", {})
            except (ValueError, json.JSONDecodeError):
                pass

        # Clean the display text — remove the raw JSON block for the chat
        display_text = text
        if brief_complete and "```json" in text:
            # Keep text before and after the JSON block
            before = text[:text.index("```json")].strip()
            after_idx = text.index("```", text.index("```json") + 7) + 3
            after = text[after_idx:].strip()
            display_text = f"{before}\n\n{after}".strip() if before else after

        return BriefAnalysisResult(
            response_text=display_text,
            brief_complete=brief_complete,
            brief_data=brief_data,
        )

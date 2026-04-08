from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.infrastructure.external.anthropic_client import AnthropicClient

CLASSIFICATION_PROMPT = """Classify this email for a creative agency's CRM. Respond ONLY with valid JSON.

{
  "message_type": "brief|feedback|negotiation|scheduling|follow_up|internal_discussion|general",
  "sentiment": "positive|neutral|negative",
  "priority": "high|medium|low",
  "entities": {
    "people": [],
    "money": [],
    "projects": [],
    "dates": []
  },
  "summary": "2-sentence summary of this email's content and significance."
}

Rules:
- message_type: brief=new project request, feedback=client feedback on deliverables, negotiation=pricing/terms, scheduling=meetings/timeline, follow_up=checking in, internal_discussion=agency internal, general=other
- priority: high=money/new brief/urgent, medium=feedback/scheduling, low=follow-ups/FYIs
- money[]: exact amounts with currency (e.g. "₹5,00,000", "$12,000")
- summary: specific about what was discussed, not generic"""


class EmailClassifier:
    def __init__(self):
        self._llm = AnthropicClient()
        self._model = get_settings().ANTHROPIC_HAIKU_MODEL

    async def classify(self, email: dict) -> dict:
        """Classify a single email. Returns classification matching EmailIndex fields."""
        content = (
            f"From: {email.get('from', '')}\n"
            f"To: {email.get('to', '')}\n"
            f"Subject: {email.get('subject', '')}\n"
            f"Date: {email.get('date', '')}\n"
            f"Snippet: {email.get('snippet', '')}"
        )

        try:
            result = await self._llm.complete_json(
                system=CLASSIFICATION_PROMPT,
                messages=[{"role": "user", "content": content}],
                model=self._model,
                max_tokens=500,
            )
            return {
                "message_type": result.get("message_type", "general"),
                "sentiment": result.get("sentiment", "neutral"),
                "priority": result.get("priority", "medium"),
                "entities": result.get("entities", {}),
                "summary": result.get("summary", email.get("snippet", "")[:200]),
            }
        except Exception:
            return {
                "message_type": "general",
                "sentiment": "neutral",
                "priority": "medium",
                "entities": {},
                "summary": email.get("snippet", "")[:200],
            }

    async def classify_batch(self, emails: list[dict], concurrency: int = 5) -> list[dict]:
        """Classify multiple emails with bounded concurrency."""
        semaphore = asyncio.Semaphore(concurrency)

        async def _classify(email: dict) -> dict:
            async with semaphore:
                return await self.classify(email)

        return await asyncio.gather(*[_classify(e) for e in emails])

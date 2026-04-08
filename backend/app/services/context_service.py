from __future__ import annotations

from app.infrastructure.external.anthropic_client import AnthropicClient

EXTRACTION_PROMPT = """You are an AI that extracts structured client intelligence from pasted communications (emails, meeting notes, chat messages, or typed context).

Given the raw text, extract a structured Client Context Profile in JSON format.

## Output format (respond ONLY with valid JSON):

```json
{
  "relationship": {
    "status": "cold_pitch | warm_intro | existing_client",
    "duration_months": null,
    "primary_contact": {
      "name": "",
      "role": "",
      "communication_style": ""
    },
    "other_contacts": [
      {"name": "", "role": "", "involvement": ""}
    ],
    "decision_chain": "",
    "typical_cycle": ""
  },
  "past_work": [
    {
      "project": "",
      "date": "",
      "value": null,
      "status": "completed | proposal_rejected | proposal_accepted | in_progress",
      "client_feedback": "",
      "lesson": ""
    }
  ],
  "pricing_intelligence": {
    "budget_signals": [],
    "price_sensitivity": "low | medium | high",
    "past_accepted_range": "",
    "past_rejected_range": "",
    "negotiation_style": ""
  },
  "preferences": {
    "communication": "",
    "creative": "",
    "process": ""
  },
  "opportunities": [
    {"signal": "", "implication": ""}
  ],
  "risks": [
    {"signal": "", "implication": ""}
  ]
}
```

## Rules:
- Extract ONLY what's explicitly stated or strongly implied in the text.
- Leave fields empty or null if the information is not present.
- For budget_signals, extract exact numbers and quotes when mentioned.
- For past_work, note both successes and failures with lessons learned.
- For risks, flag anything that could derail the proposal (price sensitivity, past complaints, competitor advantage).
- For opportunities, note signals that suggest the client is ready to buy or expand.
- Be precise with names, roles, and amounts — these feed into proposal generation."""


CONTEXT_BRIEF_PROMPT = """You are generating a Context Brief for an AI proposal copilot. Given a structured Client Context Profile (JSON), write a natural-language summary that will be injected into all AI agent prompts during proposal generation.

The brief should be actionable — tell the AI agents what this context MEANS for the proposal, not just what the facts are.

## Output format:

## Context Brief: {client_name}

**RELATIONSHIP**: [one-line summary of status, duration, key contacts]

**PAST WORK**: [summary of previous projects, outcomes, feedback]

**PRICING INTELLIGENCE**: [what they've accepted/rejected, sensitivity, negotiation patterns]

**WHAT THIS MEANS FOR THIS PROPOSAL**:
1. [specific recommendation for letter tone — e.g., "warm, reference shared history"]
2. [specific recommendation for pricing — e.g., "offer tiered pricing, they rejected flat ₹8L"]
3. [specific recommendation for scope framing — e.g., "emphasise fast revision turnaround"]
4. [any landmines to avoid — e.g., "don't price video above ₹5L"]
5. [format preferences — e.g., "send as PDF, they share internally"]

**DECISION CHAIN**: [who approves what, typical timeline]

Keep it under 300 words. Every line should change how the AI behaves."""


class ContextService:
    def __init__(self):
        self._llm = AnthropicClient()

    async def extract_context(self, raw_text: str) -> dict:
        """Parse pasted text (emails, notes, etc.) into a structured Client Context Profile."""
        if not self._llm.is_configured:
            return {"_error": "AI not configured"}

        result = await self._llm.complete_json(
            system=EXTRACTION_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Extract the client context profile from this text:\n\n{raw_text}",
            }],
            max_tokens=3000,
        )
        return result

    async def generate_context_brief(self, client_name: str, context_profile: dict) -> str:
        """Generate a natural-language Context Brief from a structured profile."""
        if not self._llm.is_configured or not context_profile:
            return ""

        import json
        profile_json = json.dumps(context_profile, indent=2, default=str)

        brief = await self._llm.complete(
            system=CONTEXT_BRIEF_PROMPT.format(client_name=client_name),
            messages=[{
                "role": "user",
                "content": f"Generate the Context Brief from this profile:\n\n{profile_json}",
            }],
            max_tokens=1500,
            temperature=0.3,
        )
        return brief

    async def merge_context(self, existing: dict, new_extraction: dict) -> dict:
        """Merge a new extraction into an existing context profile."""
        if not existing:
            return new_extraction

        # Deep merge — new data supplements existing, doesn't replace
        merged = dict(existing)

        # Merge relationship (prefer new if more detailed)
        new_rel = new_extraction.get("relationship", {})
        if new_rel:
            old_rel = merged.get("relationship", {})
            for k, v in new_rel.items():
                if v and (not old_rel.get(k) or k in ("status", "primary_contact")):
                    old_rel[k] = v
            merged["relationship"] = old_rel

        # Append past_work (avoid duplicates by project name)
        new_work = new_extraction.get("past_work", [])
        old_work = merged.get("past_work", [])
        existing_projects = {w.get("project", "").lower() for w in old_work}
        for w in new_work:
            if w.get("project", "").lower() not in existing_projects:
                old_work.append(w)
        merged["past_work"] = old_work

        # Merge pricing intelligence (append signals, update sensitivity)
        new_pricing = new_extraction.get("pricing_intelligence", {})
        old_pricing = merged.get("pricing_intelligence", {})
        if new_pricing.get("budget_signals"):
            old_signals = old_pricing.get("budget_signals", [])
            old_pricing["budget_signals"] = list(set(old_signals + new_pricing["budget_signals"]))
        for k in ("price_sensitivity", "past_accepted_range", "past_rejected_range", "negotiation_style"):
            if new_pricing.get(k):
                old_pricing[k] = new_pricing[k]
        merged["pricing_intelligence"] = old_pricing

        # Merge preferences
        new_prefs = new_extraction.get("preferences", {})
        old_prefs = merged.get("preferences", {})
        for k, v in new_prefs.items():
            if v:
                old_prefs[k] = v
        merged["preferences"] = old_prefs

        # Append opportunities and risks
        for key in ("opportunities", "risks"):
            existing_items = merged.get(key, [])
            new_items = new_extraction.get(key, [])
            existing_signals = {i.get("signal", "").lower() for i in existing_items}
            for item in new_items:
                if item.get("signal", "").lower() not in existing_signals:
                    existing_items.append(item)
            merged[key] = existing_items

        return merged

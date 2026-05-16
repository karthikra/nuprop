"""The proposal ideation side-channel.

A read-only Claude side-channel attached to each proposal. The user opens it
to think out loud about strategy / angles / pricing without polluting the
main pipeline. Nothing here mutates ``proposal.*`` fields; the only writes
are to ``chat_messages`` with ``channel="ideation"``.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_IDEATION_SYSTEM_PREAMBLE = """\
You are NUPROP's ideation copilot — a thinking partner for a senior BD lead
at a design / professional-services agency.

The user has an open proposal and wants to think out loud with you about it.
You should:
- Ask probing questions, suggest angles, surface assumptions.
- Reference what's already known about this proposal (below) when helpful.
- Be honest about trade-offs, not just agreeable.
- Keep responses tight and conversational — this is a brainstorm, not a deck.
- Never fabricate facts; if you don't know something, say so.

You can see what the agency has produced so far, but you cannot modify it.
If the user wants to apply your suggestions, they'll do that themselves in
the main proposal flow.
"""


# Truncation cutoffs (characters, first-pass heuristics — tune via real usage).
_RESEARCH_CHARS = 3000
_BENCHMARKS_CHARS = 2000
_LETTER_CHARS = 1500
_SUMMARY_CHARS = 1500


def _truncate(text: str, max_chars: int) -> str:
    """Truncate ``text`` to ``max_chars`` with a visible marker if cut."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... (truncated)"


def _inr(amount: int) -> str:
    """Format an integer rupee amount with Indian numbering (1,00,000 style)."""
    n = int(amount)
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        return sign + s
    last3 = s[-3:]
    rest = s[:-3]
    groups: list[str] = []
    while len(rest) > 2:
        groups.append(rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.append(rest)
    return sign + ",".join(reversed(groups)) + "," + last3


def _build_ideation_system_prompt(proposal) -> str:
    """Assemble the system prompt for one ideation turn.

    Gracefully handles a brand-new proposal where ``brief`` is empty and
    ``research`` / narrative fields are ``None``. Long text fields are
    truncated so the prompt stays bounded even for a fully-built proposal.
    """
    parts: list[str] = [_IDEATION_SYSTEM_PREAMBLE, "## What's known about this proposal so far\n"]

    parts.append(f"**Project name:** {proposal.project_name}")
    parts.append(
        f"**Current phase:** {(proposal.pipeline_state or {}).get('current_phase', 'brief')}"
    )

    if proposal.brief:
        parts.append(
            f"\n**Brief:**\n```json\n{json.dumps(proposal.brief, indent=2, ensure_ascii=False)}\n```"
        )
    else:
        parts.append("\n**Brief:** Not yet established — the user hasn't completed brief intake.")

    if proposal.research:
        parts.append(f"\n**Research findings:**\n{_truncate(proposal.research, _RESEARCH_CHARS)}")
    if proposal.benchmarks:
        parts.append(f"\n**Market benchmarks:**\n{_truncate(proposal.benchmarks, _BENCHMARKS_CHARS)}")

    if proposal.cost_model:
        cm = proposal.cost_model
        total = cm.get("grand_total", 0)
        items = len(cm.get("line_items", []))
        # ₹ formatting follows Indian numbering grouping (1,00,000 = 1 lakh).
        parts.append(f"\n**Cost model:** Total ₹{_inr(total)}, {items} line items.")

    if proposal.covering_letter:
        parts.append(
            f"\n**Covering letter (current draft):**\n{_truncate(proposal.covering_letter, _LETTER_CHARS)}"
        )
    if proposal.executive_summary:
        parts.append(
            f"\n**Executive summary:**\n{_truncate(proposal.executive_summary, _SUMMARY_CHARS)}"
        )

    return "\n".join(parts)


class IdeationService:
    """Worker-side runner for the ideation phase. Filled in by the next task."""

    def __init__(self, session: AsyncSession, redis):
        self.session = session
        self.redis = redis

    async def run_ideation(self, proposal_id: UUID | str) -> None:
        raise NotImplementedError  # implemented in Task 5

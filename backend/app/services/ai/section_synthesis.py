"""Pass-2 synthesis-section generators.

The two synthesis sections — executive_summary and cover_page — read the
Pass-1 fact section outputs in addition to the brief. They run sequentially
after Pass 1 completes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.services.llm import Tier, get_ai_service

logger = logging.getLogger(__name__)


def _condense_pass1(pass1_sections: dict) -> str:
    out: dict[str, str] = {}
    for key, payload in (pass1_sections or {}).items():
        content = (payload or {}).get("content")
        if content:
            out[key] = content[:3000]
    return json.dumps(out, ensure_ascii=False, indent=2)


async def _generate_executive_summary(
    brief: dict, pass1_sections: dict, context_brief: str | None, agency_name: str,
    refine_instructions: str | None = None,
) -> dict:
    user_prompt = (
        "Pass-1 sections:\n```json\n" + _condense_pass1(pass1_sections) + "\n```\n\n"
        "Brief:\n```json\n" + json.dumps(brief or {}, ensure_ascii=False, indent=2) + "\n```\n\n"
        "Write the EXECUTIVE SUMMARY of this proposal. 1-2 short paragraphs in"
        " markdown. State the problem, your solution, and the key ask (cost and"
        " timeline) up front. This stands alone for decision-makers who read only"
        " this section. Do not invent details — use only what's in the inputs."
    )
    if refine_instructions:
        user_prompt += (
            "\n\nREFINEMENT INSTRUCTIONS (the user wants the section adjusted): "
            + refine_instructions
        )
    result = await get_ai_service().complete(
        prompt=user_prompt,
        system="You are a senior proposal writer. Write directly; no preamble.",
        tier=Tier.BALANCED,
        max_tokens=1500,
    )
    return {
        "content": result.text,
        "assets": [],
        "included": True,
        "metadata": {},
    }


async def _generate_cover_page(
    brief: dict, pass1_sections: dict, context_brief: str | None, agency_name: str,
    refine_instructions: str | None = None,
) -> dict:
    project = (brief or {}).get("project") or {}
    client = (brief or {}).get("client") or {}
    project_name = project.get("name") or "Proposal"
    client_name = client.get("name") or "Client"

    exec_summary = ((pass1_sections or {}).get("executive_summary") or {}).get("content", "")

    user_prompt = (
        "Agency: " + agency_name + "\n"
        "Client: " + client_name + "\n"
        "Project: " + project_name + "\n\n"
        "Executive summary (first paragraph):\n" + exec_summary[:600] + "\n\n"
        "Write a SHORT cover-page body for a proposal. 1-2 sentences in markdown:"
        " an evocative one-line teaser that captures the engagement, plus the"
        " date. The agency name, client name, project name, and date are also"
        " sent separately as structured metadata — do not repeat them in the body."
    )
    if refine_instructions:
        user_prompt += (
            "\n\nREFINEMENT INSTRUCTIONS (the user wants the section adjusted): "
            + refine_instructions
        )
    result = await get_ai_service().complete(
        prompt=user_prompt,
        system="You are a senior proposal writer. Write a brief evocative cover-page teaser; no preamble.",
        tier=Tier.BALANCED,
        max_tokens=400,
    )

    return {
        "content": result.text,
        "assets": [],
        "included": True,
        "metadata": {
            "agency_name": agency_name,
            "client_name": client_name,
            "project_name": project_name,
            "issued_date": datetime.now(timezone.utc).date().isoformat(),
        },
    }


_SYNTHESIS_GENERATORS = {
    "executive_summary": _generate_executive_summary,
    "cover_page": _generate_cover_page,
}


async def generate_synthesis_section(
    section_type: str,
    brief: dict,
    pass1_sections: dict,
    context_brief: str | None,
    agency_name: str,
    refine_instructions: str | None = None,
) -> dict:
    """Generate one synthesis section. Raises KeyError on unknown section_type."""
    return await _SYNTHESIS_GENERATORS[section_type](
        brief, pass1_sections, context_brief, agency_name, refine_instructions,
    )

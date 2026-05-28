"""Single-section regeneration / refinement dispatch.

Extracted from the proposals view layer so that both the HTTP endpoints
(``/regenerate``, ``/refine``) and the chat ViewModel can drive a single
section through the fact-vs-synthesis generators without importing from a
view module (which would be a layering violation).

Pure dispatch: builds the agency context, routes to the fact or synthesis
generator, and returns the freshly-generated section payload. Persistence
and any WebSocket broadcast stay with the caller.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.section_facts import generate_fact_section
from app.services.ai.section_synthesis import generate_synthesis_section
from app.services.sections import FACT_SECTIONS, SECTION_ORDER


async def regenerate_section_content(
    proposal,
    section_type: str,
    refine_instructions: str | None,
    db: AsyncSession,
) -> dict:
    """Single-section dispatch shared by /regenerate and /refine."""
    from sqlalchemy import select
    from app.infrastructure.db.models.agency import Agency

    agency_row = await db.execute(select(Agency).where(Agency.id == proposal.agency_id))
    agency = agency_row.scalar_one()

    if section_type in FACT_SECTIONS:
        return await generate_fact_section(
            section_type=section_type,
            brief=proposal.brief or {},
            research=proposal.research,
            cost_model=proposal.cost_model or {},
            template_config=None,
            context_brief=proposal.context_brief,
            agency_name=agency.name,
            refine_instructions=refine_instructions,
        )
    # Synthesis section — rebuild pass1_sections dict from current proposal columns.
    # Include executive_summary AND fact sections (everything except the section being
    # regenerated, to avoid stale self-reference).
    pass1_sections = {
        s: getattr(proposal, s) or {}
        for s in SECTION_ORDER
        if s != section_type
    }
    return await generate_synthesis_section(
        section_type=section_type,
        brief=proposal.brief or {},
        pass1_sections=pass1_sections,
        context_brief=proposal.context_brief,
        agency_name=agency.name,
        refine_instructions=refine_instructions,
    )

"""Section types, canonical order, and template-defaults helper.

A NUPROP proposal is composed of nine canonical sections, persisted as nine
nullable JSON columns on the ``Proposal`` model. Each column carries the
``{content, assets, included, metadata}`` payload shape; ``SECTION_ORDER``
is the only reader/writer of canonical iteration sequence.
"""
from __future__ import annotations

import enum


class SectionType(str, enum.Enum):
    COVER_PAGE           = "cover_page"
    EXECUTIVE_SUMMARY    = "executive_summary"
    PROBLEM_STATEMENT    = "problem_statement"
    PROPOSED_SOLUTION    = "proposed_solution"
    SCOPE_OF_WORK        = "scope_of_work"
    TIMELINE             = "timeline"
    PRICING              = "pricing"
    QUALIFICATIONS       = "qualifications"
    TERMS_AND_CONDITIONS = "terms_and_conditions"


SECTION_ORDER: list[str] = [
    SectionType.COVER_PAGE.value,
    SectionType.EXECUTIVE_SUMMARY.value,
    SectionType.PROBLEM_STATEMENT.value,
    SectionType.PROPOSED_SOLUTION.value,
    SectionType.SCOPE_OF_WORK.value,
    SectionType.TIMELINE.value,
    SectionType.PRICING.value,
    SectionType.QUALIFICATIONS.value,
    SectionType.TERMS_AND_CONDITIONS.value,
]

FACT_SECTIONS: list[str] = [
    SectionType.PROBLEM_STATEMENT.value,
    SectionType.PROPOSED_SOLUTION.value,
    SectionType.SCOPE_OF_WORK.value,
    SectionType.TIMELINE.value,
    SectionType.PRICING.value,
    SectionType.QUALIFICATIONS.value,
    SectionType.TERMS_AND_CONDITIONS.value,
]

SYNTHESIS_SECTIONS: list[str] = [
    SectionType.EXECUTIVE_SUMMARY.value,
    SectionType.COVER_PAGE.value,
]


def empty_section() -> dict:
    """The neutral payload for a section that exists but has no content yet."""
    return {"content": "", "assets": [], "included": True, "metadata": {}}


def default_sections_for_template(template_config: dict | None) -> set[str]:
    """Which section types are 'on by default' for this template.

    Templates may declare ``config.default_sections: list[str]``; otherwise all
    nine sections are included. Unknown section names in the template config
    are silently dropped.
    """
    if not template_config or "default_sections" not in template_config:
        return set(SECTION_ORDER)
    declared = template_config.get("default_sections") or []
    return {s for s in declared if s in SECTION_ORDER}

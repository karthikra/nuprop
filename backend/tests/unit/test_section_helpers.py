from __future__ import annotations

from app.services.sections import (
    FACT_SECTIONS,
    SECTION_ORDER,
    SYNTHESIS_SECTIONS,
    SectionType,
    default_sections_for_template,
    empty_section,
)


def test_section_order_has_nine_entries_in_canonical_sequence():
    assert SECTION_ORDER == [
        "cover_page",
        "executive_summary",
        "problem_statement",
        "proposed_solution",
        "scope_of_work",
        "timeline",
        "pricing",
        "qualifications",
        "terms_and_conditions",
    ]


def test_fact_and_synthesis_partition_covers_all_sections_disjointly():
    assert set(FACT_SECTIONS) | set(SYNTHESIS_SECTIONS) == set(SECTION_ORDER)
    assert not (set(FACT_SECTIONS) & set(SYNTHESIS_SECTIONS))
    assert len(FACT_SECTIONS) == 7
    assert len(SYNTHESIS_SECTIONS) == 2


def test_section_type_enum_values_match_section_order():
    assert {s.value for s in SectionType} == set(SECTION_ORDER)


def test_empty_section_returns_default_payload_shape():
    s = empty_section()
    assert s == {"content": "", "assets": [], "included": True, "metadata": {}}
    s["assets"].append("contaminated")
    assert empty_section()["assets"] == []


def test_default_sections_for_template_returns_all_nine_when_no_template():
    assert default_sections_for_template(None) == set(SECTION_ORDER)


def test_default_sections_for_template_returns_all_nine_when_template_lacks_default_sections():
    assert default_sections_for_template({"narrative": {}}) == set(SECTION_ORDER)


def test_default_sections_for_template_returns_specified_subset_from_template_config():
    cfg = {"default_sections": ["problem_statement", "pricing", "executive_summary"]}
    assert default_sections_for_template(cfg) == {"problem_statement", "pricing", "executive_summary"}


def test_default_sections_for_template_ignores_unknown_section_names():
    cfg = {"default_sections": ["pricing", "not_a_real_section", "executive_summary"]}
    assert default_sections_for_template(cfg) == {"pricing", "executive_summary"}

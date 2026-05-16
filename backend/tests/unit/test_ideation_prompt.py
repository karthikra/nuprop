"""Unit tests for the ideation system-prompt builder."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.ideation_service import _build_ideation_system_prompt, _inr


def _proposal(**overrides):
    base = dict(
        project_name="Pepsi Global Dashboard",
        brief={},
        research=None,
        benchmarks=None,
        cost_model=None,
        covering_letter=None,
        executive_summary=None,
        pipeline_state={"current_phase": "brief"},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_empty_proposal_states_brief_is_not_yet_established():
    prompt = _build_ideation_system_prompt(_proposal())
    assert "Project name:" in prompt and "Pepsi Global Dashboard" in prompt
    assert "Current phase:" in prompt and "brief" in prompt
    assert "**Brief:** Not yet established" in prompt
    # No reference to research / cost model when those fields are absent.
    assert "Research findings" not in prompt
    assert "Cost model" not in prompt
    assert "Covering letter" not in prompt


def test_full_proposal_includes_each_known_section():
    p = _proposal(
        brief={"client": {"name": "Pepsi Global"}},
        research="## Pepsi Global research\nLong paragraph " + "x" * 5000,
        benchmarks="## Benchmarks\nLong paragraph " + "y" * 3000,
        cost_model={"grand_total": 1480000, "line_items": [{}] * 6},
        covering_letter="Dear Pepsi team," + " z" * 2000,
        executive_summary="Summary " + " w" * 2000,
        pipeline_state={"current_phase": "narrative_review"},
    )
    prompt = _build_ideation_system_prompt(p)
    assert "**Project name:** Pepsi Global Dashboard" in prompt
    assert "**Current phase:** narrative_review" in prompt
    assert "**Research findings:**" in prompt
    assert "**Market benchmarks:**" in prompt
    assert "Total ₹14,80,000" in prompt
    assert "6 line items" in prompt
    assert "Covering letter" in prompt
    assert "Executive summary" in prompt


def test_long_fields_are_truncated_with_a_marker():
    p = _proposal(research="a" * 10000)
    prompt = _build_ideation_system_prompt(p)
    assert "... (truncated)" in prompt
    # The truncated body must be present but bounded.
    research_idx = prompt.index("Research findings")
    assert prompt.count("a", research_idx) <= 3100  # 3000 cap + a little slack


def test_preamble_describes_the_read_only_invariant():
    prompt = _build_ideation_system_prompt(_proposal())
    assert "ideation copilot" in prompt
    assert "cannot modify" in prompt


def test_none_pipeline_state_falls_back_to_brief():
    prompt = _build_ideation_system_prompt(_proposal(pipeline_state=None))
    assert "**Current phase:** brief" in prompt


def test_inr_indian_numbering_edge_cases():
    assert _inr(0) == "0"
    assert _inr(999) == "999"
    assert _inr(1000) == "1,000"
    assert _inr(100000) == "1,00,000"
    assert _inr(1480000) == "14,80,000"
    assert _inr(10000000) == "1,00,00,000"
    # negative numbers — guard against the sign-as-group bug
    assert _inr(-1480000) == "-14,80,000"

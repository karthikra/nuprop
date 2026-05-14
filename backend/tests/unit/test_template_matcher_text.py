"""Unit tests for app.services.ai.template_matcher._brief_to_text.

The DB-backed ``match()`` method is covered in
tests/integration/test_repositories.py via seeded templates.
"""

from __future__ import annotations

from app.services.ai.template_matcher import TemplateMatcher


def test_brief_to_text_flattens_project_and_client_fields():
    matcher = TemplateMatcher()
    brief = {
        "project": {
            "type": "rebrand",
            "deliverables": [
                {"category": "Logo", "details": "new mark"},
                {"category": "Guidelines", "details": "brand book"},
            ],
            "timeline": "3 months",
        },
        "client": {"industry": "fintech"},
    }
    text = matcher._brief_to_text(brief)
    for token in ("rebrand", "Logo", "new mark", "Guidelines", "brand book", "3 months", "fintech"):
        assert token in text


def test_brief_to_text_handles_empty_brief():
    assert TemplateMatcher()._brief_to_text({}) == ""


def test_brief_to_text_handles_partial_brief():
    matcher = TemplateMatcher()
    text = matcher._brief_to_text({"client": {"industry": "retail"}})
    assert "retail" in text

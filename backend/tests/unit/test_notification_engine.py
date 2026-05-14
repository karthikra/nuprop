"""Unit tests for app.services.notification_engine — the 6 alert rules."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.notification_engine import evaluate_rules


def _visitor(session_count=1):
    return SimpleNamespace(session_count=session_count)


def _proposal(name="Acme Rebrand"):
    return SimpleNamespace(project_name=name)


def test_no_events_yields_no_candidates():
    assert evaluate_rules([], _visitor(), _proposal(), 0, 0, 1) == []


def test_first_view_fires_on_first_session_page_view():
    out = evaluate_rules([{"t": "page_view"}], _visitor(1), _proposal(), 0, 0, 1)
    assert any(c.alert_type == "first_view" for c in out)


def test_return_visit_fires_on_later_session_not_first_view():
    out = evaluate_rules([{"t": "page_view"}], _visitor(3), _proposal(), 0, 0, 1)
    types = {c.alert_type for c in out}
    assert "return_visit" in types
    assert "first_view" not in types


def test_pdf_download_candidate_created():
    out = evaluate_rules(
        [{"t": "cta_click", "cta": "Download PDF"}], _visitor(2), _proposal(), 0, 0, 1
    )
    assert any(c.alert_type == "pdf_download" for c in out)


def test_non_download_cta_click_is_high_urgency():
    out = evaluate_rules(
        [{"t": "cta_click", "cta": "Book a call"}], _visitor(2), _proposal(), 0, 0, 1
    )
    cta = [c for c in out if c.alert_type == "cta_click"]
    assert len(cta) == 1
    assert cta[0].urgency == "high"


def test_download_does_not_also_fire_generic_cta_click():
    out = evaluate_rules(
        [{"t": "cta_click", "cta": "Download the PDF"}], _visitor(2), _proposal(), 0, 0, 1
    )
    assert any(c.alert_type == "pdf_download" for c in out)
    assert not any(c.alert_type == "cta_click" for c in out)


def test_high_engagement_fires_only_when_threshold_is_crossed():
    crossed = evaluate_rules([], _visitor(2), _proposal(), previous_score=55, new_score=65, visitor_count=1)
    assert any(c.alert_type == "high_engagement" for c in crossed)

    # already above 60 before this batch — must not fire again
    already = evaluate_rules([], _visitor(2), _proposal(), previous_score=70, new_score=80, visitor_count=1)
    assert not any(c.alert_type == "high_engagement" for c in already)


def test_new_visitor_fires_when_proposal_was_forwarded():
    # first session for this visitor, but the proposal already has other visitors
    out = evaluate_rules([{"t": "page_view"}], _visitor(1), _proposal(), 0, 0, visitor_count=3)
    assert any(c.alert_type == "new_visitor" for c in out)


def test_candidate_messages_include_project_name():
    out = evaluate_rules([{"t": "page_view"}], _visitor(1), _proposal("Globex Launch"), 0, 0, 1)
    assert all("Globex Launch" in c.message for c in out)

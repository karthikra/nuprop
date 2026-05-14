"""Unit tests for app.services.engagement_scorer — the 8-factor scoring model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.engagement_scorer import (
    EngagementBreakdown,
    compute_proposal_score,
    compute_visitor_score,
)


# ── EngagementBreakdown ──────────────────────────────────────────────────────
def test_empty_breakdown_is_zero_and_cold():
    b = EngagementBreakdown()
    assert b.total == 0
    assert b.classification == "cold"


def test_breakdown_total_caps_at_100():
    b = EngagementBreakdown(
        opened_within_24h=10, time_on_site=20, sections_viewed=15,
        cards_expanded=15, investment_time=10, pdf_downloaded=5,
        return_visits=15, cta_clicked=50,  # raw sum well over 100
    )
    assert b.total == 100


def test_breakdown_classification_thresholds():
    assert EngagementBreakdown(time_on_site=20).classification == "cold"   # 20
    assert EngagementBreakdown(time_on_site=21).classification == "cool"   # 21
    assert EngagementBreakdown(time_on_site=41).classification == "warm"   # 41
    assert EngagementBreakdown(time_on_site=61).classification == "hot"    # 61
    assert EngagementBreakdown(time_on_site=81).classification == "ready"  # 81


def test_breakdown_to_dict_includes_derived_fields():
    d = EngagementBreakdown(time_on_site=8, cta_clicked=10).to_dict()
    assert d["total"] == 18
    assert d["classification"] == "cold"
    assert d["time_on_site"] == 8


# ── compute_visitor_score: factor 1 — opened within 24h ──────────────────────
def test_opened_within_24h_awarded_when_viewed_promptly():
    sent = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    first = sent + timedelta(hours=5)
    b = compute_visitor_score([], 1, 0, first, sent)
    assert b.opened_within_24h == 10


def test_opened_within_24h_not_awarded_when_viewed_late():
    sent = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    first = sent + timedelta(hours=30)
    b = compute_visitor_score([], 1, 0, first, sent)
    assert b.opened_within_24h == 0


def test_opened_within_24h_handles_naive_datetimes():
    sent = datetime(2026, 1, 1, 12, 0)   # naive
    first = datetime(2026, 1, 1, 14, 0)  # naive
    b = compute_visitor_score([], 1, 0, first, sent)
    assert b.opened_within_24h == 10


# ── factor 2 — time on site ──────────────────────────────────────────────────
def test_time_on_site_tiers():
    assert compute_visitor_score([], 1, 59, None, None).time_on_site == 0
    assert compute_visitor_score([], 1, 60, None, None).time_on_site == 8
    assert compute_visitor_score([], 1, 180, None, None).time_on_site == 14
    assert compute_visitor_score([], 1, 300, None, None).time_on_site == 20


# ── factor 3 — sections viewed ───────────────────────────────────────────────
def test_sections_viewed_counts_distinct_section_enters():
    events = [
        {"t": "section_enter", "section": "intro"},
        {"t": "section_enter", "section": "intro"},   # duplicate — ignored
        {"t": "section_enter", "section": "scope"},
        {"t": "section_enter", "section": "investment"},
    ]
    # 3 of 7 sections = 0.43 -> only the ">0" tier -> 3
    assert compute_visitor_score(events, 1, 0, None, None, total_sections=7).sections_viewed == 3


def test_sections_viewed_high_coverage_tier():
    events = [{"t": "section_enter", "section": s}
              for s in ("a", "b", "c", "d", "e", "f")]
    # 6 of 7 = 0.857 -> >0.75 -> 15
    assert compute_visitor_score(events, 1, 0, None, None, total_sections=7).sections_viewed == 15


def test_event_type_and_section_id_key_variants_supported():
    events = [
        {"event_type": "section_enter", "section_id": "intro"},
        {"event_type": "section_enter", "section_id": "scope"},
    ]
    assert compute_visitor_score(events, 1, 0, None, None, total_sections=2).sections_viewed == 15


# ── factor 4 — cards expanded ────────────────────────────────────────────────
def test_cards_expanded_tiers():
    def cards(n):
        return [{"t": "card_expand", "card": f"c{i}"} for i in range(n)]

    assert compute_visitor_score(cards(0), 1, 0, None, None).cards_expanded == 0
    assert compute_visitor_score(cards(1), 1, 0, None, None).cards_expanded == 5
    assert compute_visitor_score(cards(3), 1, 0, None, None).cards_expanded == 10
    assert compute_visitor_score(cards(5), 1, 0, None, None).cards_expanded == 15


# ── factor 5 — investment-section time ───────────────────────────────────────
def test_investment_time_from_section_exit_durations():
    events = [
        {"t": "section_exit", "section": "investment", "duration": 80},
        {"t": "section_exit", "section": "cost", "duration": 50},
    ]  # 130 > 120 -> 10
    assert compute_visitor_score(events, 1, 0, None, None).investment_time == 10


def test_investment_time_mid_tier():
    events = [{"t": "section_exit", "section": "investment", "duration": 40}]  # >30 -> 5
    assert compute_visitor_score(events, 1, 0, None, None).investment_time == 5


# ── factors 6 & 8 — pdf download / cta click ─────────────────────────────────
def test_pdf_download_and_cta_click_both_detected():
    events = [{"t": "cta_click", "cta": "Download PDF"}]
    b = compute_visitor_score(events, 1, 0, None, None)
    assert b.pdf_downloaded == 5
    assert b.cta_clicked == 10


def test_non_download_cta_does_not_award_pdf():
    events = [{"t": "cta_click", "cta": "Book a call"}]
    b = compute_visitor_score(events, 1, 0, None, None)
    assert b.pdf_downloaded == 0
    assert b.cta_clicked == 10


# ── factor 7 — return visits ─────────────────────────────────────────────────
def test_return_visits_tiers():
    assert compute_visitor_score([], 1, 0, None, None).return_visits == 0
    assert compute_visitor_score([], 2, 0, None, None).return_visits == 8
    assert compute_visitor_score([], 3, 0, None, None).return_visits == 15


# ── compute_proposal_score ───────────────────────────────────────────────────
def test_proposal_score_empty_is_zero():
    assert compute_proposal_score([]) == 0


def test_proposal_score_uses_max_plus_visitor_bonus():
    a = EngagementBreakdown(time_on_site=20)  # total 20
    b = EngagementBreakdown(time_on_site=40)  # total 40
    assert compute_proposal_score([a]) == 20          # single visitor, no bonus
    assert compute_proposal_score([a, b]) == 45       # max 40 + 5 (2 visitors)
    assert compute_proposal_score([a, b, a]) == 50    # max 40 + 10 (3+ visitors)


def test_proposal_score_caps_at_100():
    high = EngagementBreakdown(time_on_site=100)  # total caps at 100
    assert compute_proposal_score([high, high, high]) == 100

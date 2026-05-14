"""Unit tests for app.services.context_intelligence — quality scoring,
preference overrides, and the sentiment timeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.context_intelligence import (
    build_sentiment_timeline,
    compute_quality_score,
    generate_preference_overrides,
)


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ── compute_quality_score ────────────────────────────────────────────────────
def test_empty_profile_scores_thin():
    score = compute_quality_score({})
    assert score.total == 0
    assert score.level == "thin"
    assert score.description


def test_recency_awarded_for_recent_source_sync():
    score = compute_quality_score({"_sources": {"gmail": {"last_sync": _iso_days_ago(5)}}})
    assert score.recency == 25


def test_recency_not_awarded_for_old_sync():
    score = compute_quality_score({"_sources": {"gmail": {"last_sync": _iso_days_ago(200)}}})
    assert score.recency == 0


def test_volume_tiers_on_interaction_count():
    assert compute_quality_score({"_sources": {"gmail": {"email_count": 4}}}).volume == 10
    assert compute_quality_score({"_sources": {"gmail": {"email_count": 15}}}).volume == 20


def test_depth_awarded_for_pricing_intelligence():
    profile = {"pricing_intelligence": {"budget_signals": ["~50L mentioned"]}}
    assert compute_quality_score(profile).depth == 20


def test_quality_level_thresholds_for_rich_profile():
    profile = {
        "_sources": {
            "gmail": {"last_sync": _iso_days_ago(1), "email_count": 20},
            "slack": {"mention_count": 5},
        },
        "pricing_intelligence": {"past_accepted_range": "40-60L"},
        "relationship": {"status": "existing_client", "decision_chain": "CMO -> CEO"},
        "past_work": [{"status": "completed", "date": _iso_days_ago(10)}],
    }
    score = compute_quality_score(profile)
    assert score.total >= 61
    assert score.level in ("rich", "full")


# ── generate_preference_overrides ────────────────────────────────────────────
def test_no_overrides_for_empty_profile():
    assert generate_preference_overrides({}) == []


def test_tiered_pricing_override_on_past_price_rejection():
    profile = {"past_work": [
        {"status": "proposal_rejected", "client_feedback": "too expensive for us"}
    ]}
    overrides = generate_preference_overrides(profile)
    assert any(o.key == "pricing_model" and o.value == "tiered" for o in overrides)


def test_warm_letter_override_for_existing_client():
    overrides = generate_preference_overrides({"relationship": {"status": "existing_client"}})
    assert any(o.key == "letter_strategy" and o.value == "warm" for o in overrides)


def test_negotiation_buffer_override_on_high_price_sensitivity():
    overrides = generate_preference_overrides(
        {"pricing_intelligence": {"price_sensitivity": "high"}}
    )
    assert any(o.key == "negotiation_buffer" for o in overrides)


def test_one_pager_override_for_finance_approver_in_decision_chain():
    profile = {"relationship": {"other_contacts": [{"role": "CFO"}]}}
    overrides = generate_preference_overrides(profile)
    assert any(o.key == "generate_one_pager" for o in overrides)


def test_scope_note_override_on_revision_friction_risk():
    profile = {"risks": [{"signal": "complained about slow revision turnaround"}]}
    overrides = generate_preference_overrides(profile)
    assert any(o.key == "scope_note" for o in overrides)


# ── build_sentiment_timeline ─────────────────────────────────────────────────
def test_sentiment_timeline_orders_dated_events_before_undated():
    profile = {
        "past_work": [
            {"status": "completed", "date": "2025-06-01", "project": "Site", "client_feedback": "great"},
            {"status": "proposal_rejected", "date": "2025-01-15", "project": "App", "client_feedback": "price"},
        ],
        "risks": [{"signal": "slow approvals"}],
    }
    timeline = build_sentiment_timeline(profile)
    assert [e.date for e in timeline][:2] == ["2025-01-15", "2025-06-01"]
    assert timeline[-1].date == ""              # undated risk sorts last
    assert timeline[-1].sentiment == "negative"


def test_sentiment_timeline_maps_work_statuses_to_sentiment():
    profile = {"past_work": [
        {"status": "completed", "date": "2025-01-01", "project": "X", "client_feedback": "smooth"},
        {"status": "proposal_accepted", "date": "2025-02-01", "project": "Y"},
        {"status": "proposal_rejected", "date": "2025-03-01", "project": "Z", "client_feedback": "budget"},
    ]}
    by_date = {e.date: e.sentiment for e in build_sentiment_timeline(profile)}
    assert by_date["2025-01-01"] == "positive"
    assert by_date["2025-02-01"] == "positive"
    assert by_date["2025-03-01"] == "negative"

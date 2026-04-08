from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NotificationCandidate:
    alert_type: str
    message: str
    urgency: str  # "normal" or "high"


def evaluate_rules(
    events: list[dict],
    visitor,
    proposal,
    previous_score: int,
    new_score: int,
    visitor_count: int,
) -> list[NotificationCandidate]:
    """Evaluate notification rules against a batch of events. Returns candidates to create."""
    candidates = []
    project = proposal.project_name or "a proposal"

    has_page_view = any(e.get("t") == "page_view" for e in events)
    has_cta = any(e.get("t") == "cta_click" for e in events)
    has_download = any(
        e.get("t") == "cta_click" and "download" in str(e.get("cta", "")).lower()
        for e in events
    )

    # 1. First view
    if has_page_view and visitor.session_count == 1:
        candidates.append(NotificationCandidate(
            alert_type="first_view",
            message=f'"{project}" was opened for the first time',
            urgency="normal",
        ))

    # 2. Return visit
    elif has_page_view and visitor.session_count > 1:
        candidates.append(NotificationCandidate(
            alert_type="return_visit",
            message=f'Someone returned to view "{project}" (visit #{visitor.session_count})',
            urgency="normal",
        ))

    # 3. PDF download
    if has_download:
        candidates.append(NotificationCandidate(
            alert_type="pdf_download",
            message=f'PDF downloaded from "{project}"',
            urgency="normal",
        ))

    # 4. CTA click (non-download)
    if has_cta and not has_download:
        candidates.append(NotificationCandidate(
            alert_type="cta_click",
            message=f'CTA clicked on "{project}" — follow up now',
            urgency="high",
        ))

    # 5. High engagement threshold crossed
    if new_score >= 60 and previous_score < 60:
        candidates.append(NotificationCandidate(
            alert_type="high_engagement",
            message=f'"{project}" reached high engagement (score: {new_score})',
            urgency="high",
        ))

    # 6. New unique visitor (forwarded)
    if has_page_view and visitor.session_count == 1 and visitor_count > 1:
        candidates.append(NotificationCandidate(
            alert_type="new_visitor",
            message=f'New person viewing "{project}" — may have been forwarded',
            urgency="normal",
        ))

    return candidates

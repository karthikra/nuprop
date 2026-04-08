from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class EngagementBreakdown:
    opened_within_24h: int = 0
    time_on_site: int = 0
    sections_viewed: int = 0
    cards_expanded: int = 0
    investment_time: int = 0
    pdf_downloaded: int = 0
    return_visits: int = 0
    cta_clicked: int = 0

    @property
    def total(self) -> int:
        return min(100, (
            self.opened_within_24h + self.time_on_site + self.sections_viewed +
            self.cards_expanded + self.investment_time + self.pdf_downloaded +
            self.return_visits + self.cta_clicked
        ))

    @property
    def classification(self) -> str:
        t = self.total
        if t >= 81:
            return "ready"
        if t >= 61:
            return "hot"
        if t >= 41:
            return "warm"
        if t >= 21:
            return "cool"
        return "cold"

    def to_dict(self) -> dict:
        return {
            "opened_within_24h": self.opened_within_24h,
            "time_on_site": self.time_on_site,
            "sections_viewed": self.sections_viewed,
            "cards_expanded": self.cards_expanded,
            "investment_time": self.investment_time,
            "pdf_downloaded": self.pdf_downloaded,
            "return_visits": self.return_visits,
            "cta_clicked": self.cta_clicked,
            "total": self.total,
            "classification": self.classification,
        }


def compute_visitor_score(
    events: list[dict],
    session_count: int,
    total_time_seconds: int,
    first_seen: datetime | None,
    sent_at: datetime | None,
    total_sections: int = 7,
) -> EngagementBreakdown:
    """Score a single visitor based on their events and stats."""
    b = EngagementBreakdown()

    # 1. Opened within 24h of send
    if sent_at and first_seen:
        sent_aware = sent_at if sent_at.tzinfo else sent_at.replace(tzinfo=timezone.utc)
        first_aware = first_seen if first_seen.tzinfo else first_seen.replace(tzinfo=timezone.utc)
        if first_aware - sent_aware < timedelta(hours=24):
            b.opened_within_24h = 10

    # 2. Time on site
    t = total_time_seconds
    if t >= 300:
        b.time_on_site = 20
    elif t >= 180:
        b.time_on_site = 14
    elif t >= 60:
        b.time_on_site = 8

    # 3. Sections viewed
    sections_seen = set()
    for e in events:
        if e.get("t") == "section_enter" or e.get("event_type") == "section_enter":
            sid = e.get("section") or e.get("section_id")
            if sid:
                sections_seen.add(sid)
    if total_sections > 0:
        pct = len(sections_seen) / total_sections
        if pct > 0.75:
            b.sections_viewed = 15
        elif pct > 0.5:
            b.sections_viewed = 8
        elif pct > 0:
            b.sections_viewed = 3

    # 4. Cards expanded
    cards = set()
    for e in events:
        et = e.get("t") or e.get("event_type")
        if et == "card_expand":
            cid = e.get("card") or e.get("card_id")
            if cid:
                cards.add(cid)
    n_cards = len(cards)
    if n_cards >= 5:
        b.cards_expanded = 15
    elif n_cards >= 3:
        b.cards_expanded = 10
    elif n_cards >= 1:
        b.cards_expanded = 5

    # 5. Investment section time
    inv_time = 0
    for e in events:
        et = e.get("t") or e.get("event_type")
        sid = e.get("section") or e.get("section_id", "")
        if et == "section_exit" and sid in ("investment", "cost"):
            dur = e.get("duration", 0)
            if isinstance(dur, (int, float)):
                inv_time += dur
    if inv_time > 120:
        b.investment_time = 10
    elif inv_time > 30:
        b.investment_time = 5

    # 6. PDF downloaded
    for e in events:
        et = e.get("t") or e.get("event_type")
        if et == "cta_click":
            cta = e.get("cta", "")
            if "download" in str(cta).lower() or "pdf" in str(cta).lower():
                b.pdf_downloaded = 5
                break

    # 7. Return visits
    rv = session_count - 1
    if rv >= 2:
        b.return_visits = 15
    elif rv == 1:
        b.return_visits = 8

    # 8. CTA clicked
    for e in events:
        et = e.get("t") or e.get("event_type")
        if et == "cta_click":
            b.cta_clicked = 10
            break

    return b


def compute_proposal_score(visitor_scores: list[EngagementBreakdown]) -> int:
    """Proposal score = max visitor score + bonus for multiple viewers."""
    if not visitor_scores:
        return 0
    max_score = max(s.total for s in visitor_scores)
    n_visitors = len(visitor_scores)
    bonus = 0
    if n_visitors >= 3:
        bonus = 10
    elif n_visitors >= 2:
        bonus = 5
    return min(100, max_score + bonus)

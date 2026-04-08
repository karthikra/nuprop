from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class ContextQualityScore:
    recency: int = 0          # +25 if interaction in last 30 days
    volume: int = 0           # +20 if >10 interactions
    depth: int = 0            # +20 if pricing data available
    breadth: int = 0          # +15 if multiple data sources
    past_work: int = 0        # +10 if completed projects exist
    decision_chain: int = 0   # +10 if decision-making process known

    @property
    def total(self) -> int:
        return min(100, self.recency + self.volume + self.depth + self.breadth + self.past_work + self.decision_chain)

    @property
    def level(self) -> str:
        t = self.total
        if t >= 81:
            return "full"
        if t >= 61:
            return "rich"
        if t >= 31:
            return "moderate"
        return "thin"

    @property
    def description(self) -> str:
        levels = {
            "full": "Deep context — autonomous preference overrides are reliable",
            "rich": "Strong context — auto-suggest preferences, reference past work",
            "moderate": "Some context — calibrate tone, verify pricing assumptions",
            "thin": "Limited context — treat as cold pitch, rely on web research",
        }
        return levels.get(self.level, "")

    def to_dict(self) -> dict:
        return {
            "recency": self.recency,
            "volume": self.volume,
            "depth": self.depth,
            "breadth": self.breadth,
            "past_work": self.past_work,
            "decision_chain": self.decision_chain,
            "total": self.total,
            "level": self.level,
            "description": self.description,
        }


@dataclass
class PreferenceOverride:
    key: str          # preference key (letter_strategy, pricing_model, etc.)
    value: str        # suggested value
    reason: str       # why this override is suggested
    confidence: str   # high/medium/low


@dataclass
class SentimentEvent:
    date: str
    sentiment: str   # positive/negative/neutral
    event: str       # description


def compute_quality_score(profile: dict) -> ContextQualityScore:
    """Score the richness of a client's context profile (0-100)."""
    score = ContextQualityScore()

    # Recency: interaction in last 30 days
    sources = profile.get("_sources", {})
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=30)

    for source_data in sources.values():
        if isinstance(source_data, dict):
            last_sync = source_data.get("last_sync")
            if last_sync:
                try:
                    sync_dt = datetime.fromisoformat(str(last_sync).replace("Z", "+00:00"))
                    if sync_dt >= threshold:
                        score.recency = 25
                        break
                except Exception:
                    pass

    # Also check past_work dates
    if score.recency == 0:
        for work in profile.get("past_work", []):
            date_str = work.get("date", "")
            if date_str:
                try:
                    work_dt = datetime.fromisoformat(str(date_str))
                    if work_dt.tzinfo is None:
                        work_dt = work_dt.replace(tzinfo=timezone.utc)
                    if work_dt >= threshold:
                        score.recency = 25
                        break
                except Exception:
                    pass

    # Volume: count total interactions
    interaction_count = 0
    for source_data in sources.values():
        if isinstance(source_data, dict):
            interaction_count += source_data.get("email_count", 0)
            interaction_count += source_data.get("meeting_count", 0)
            interaction_count += source_data.get("mention_count", 0)
            interaction_count += source_data.get("document_count", 0)
    interaction_count += len(profile.get("past_work", []))
    if interaction_count > 10:
        score.volume = 20
    elif interaction_count > 3:
        score.volume = 10

    # Depth: pricing data available
    pricing = profile.get("pricing_intelligence", {})
    if pricing.get("budget_signals") or pricing.get("past_accepted_range") or pricing.get("past_rejected_range"):
        score.depth = 20
    elif pricing.get("price_sensitivity"):
        score.depth = 10

    # Breadth: multiple data sources
    source_count = len(sources)
    has_manual = bool(profile.get("relationship", {}).get("status"))
    if has_manual:
        source_count += 1
    if source_count >= 3:
        score.breadth = 15
    elif source_count >= 2:
        score.breadth = 10
    elif source_count >= 1:
        score.breadth = 5

    # Past work: completed projects
    past_work = profile.get("past_work", [])
    completed = [w for w in past_work if w.get("status") in ("completed", "proposal_accepted")]
    if completed:
        score.past_work = 10

    # Decision chain known
    rel = profile.get("relationship", {})
    if rel.get("decision_chain") or rel.get("typical_cycle"):
        score.decision_chain = 10
    elif len(rel.get("other_contacts", [])) > 0:
        score.decision_chain = 5

    return score


def generate_preference_overrides(profile: dict) -> list[PreferenceOverride]:
    """Generate automatic preference overrides based on context signals."""
    overrides = []
    pricing = profile.get("pricing_intelligence", {})
    rel = profile.get("relationship", {})
    prefs = profile.get("preferences", {})
    past_work = profile.get("past_work", [])
    risks = profile.get("risks", [])

    # 1. Past proposal rejected for price → tiered pricing
    rejected = [w for w in past_work if w.get("status") == "proposal_rejected"]
    price_rejection = any("price" in str(w.get("client_feedback", "")).lower() or "expensive" in str(w.get("client_feedback", "")).lower() for w in rejected)
    if price_rejection:
        overrides.append(PreferenceOverride(
            key="pricing_model",
            value="tiered",
            reason="Past proposal was rejected for price — tiered gives the client budget options",
            confidence="high",
        ))

    # 2. High price sensitivity → add negotiation buffer
    if pricing.get("price_sensitivity") == "high":
        overrides.append(PreferenceOverride(
            key="negotiation_buffer",
            value="12",
            reason=f"High price sensitivity — build in 12% negotiation buffer",
            confidence="medium",
        ))

    # 3. Deep relationship → warm letter tone
    duration = rel.get("duration_months")
    status = rel.get("status", "")
    if status == "existing_client" or (isinstance(duration, (int, float)) and duration > 6):
        overrides.append(PreferenceOverride(
            key="letter_strategy",
            value="warm",
            reason="Deep existing relationship — warm tone references shared history",
            confidence="high",
        ))

    # 4. Client prefers PDFs → docx_first
    comm_prefs = prefs.get("communication", "").lower()
    if "pdf" in comm_prefs or "shares pdf" in comm_prefs:
        overrides.append(PreferenceOverride(
            key="primary_format",
            value="docx_first",
            reason="Client shares PDFs internally — prioritize document output",
            confidence="medium",
        ))

    # 5. Revision complaints → add scope note
    revision_risk = any("revision" in str(r.get("signal", "")).lower() or "delay" in str(r.get("signal", "")).lower() for r in risks)
    if revision_risk:
        overrides.append(PreferenceOverride(
            key="scope_note",
            value="48hr_revision_turnaround",
            reason="Past friction on revision speed — commit to 48hr turnaround",
            confidence="high",
        ))

    # 6. Known CFO/finance approver → generate one-pager
    other_contacts = rel.get("other_contacts", [])
    has_finance_approver = any(
        any(kw in str(c.get("role", "")).lower() for kw in ("cfo", "finance", "vp", "director"))
        for c in other_contacts
    )
    if has_finance_approver:
        overrides.append(PreferenceOverride(
            key="generate_one_pager",
            value="true",
            reason="Decision chain includes finance/VP — generate one-pager for their review",
            confidence="medium",
        ))

    return overrides


def build_sentiment_timeline(profile: dict) -> list[SentimentEvent]:
    """Build a chronological sentiment timeline from the context profile."""
    events = []

    # From past_work
    for work in profile.get("past_work", []):
        date = work.get("date", "")
        status = work.get("status", "")
        project = work.get("project", "Unknown project")
        feedback = work.get("client_feedback", "")

        if status == "completed":
            sentiment = "positive"
            if "complain" in feedback.lower() or "delay" in feedback.lower() or "issue" in feedback.lower():
                sentiment = "mixed"
            events.append(SentimentEvent(date=date, sentiment=sentiment, event=f"{project} delivered — {feedback[:80]}"))
        elif status == "proposal_rejected":
            events.append(SentimentEvent(date=date, sentiment="negative", event=f"{project} proposal rejected — {feedback[:80]}"))
        elif status == "proposal_accepted":
            events.append(SentimentEvent(date=date, sentiment="positive", event=f"{project} proposal accepted"))

    # From risks (implied negative)
    for risk in profile.get("risks", []):
        events.append(SentimentEvent(date="", sentiment="negative", event=f"Risk: {risk.get('signal', '')}"))

    # From opportunities (implied positive)
    for opp in profile.get("opportunities", []):
        events.append(SentimentEvent(date="", sentiment="positive", event=f"Opportunity: {opp.get('signal', '')}"))

    # Sort by date (dated events first, undated at end)
    dated = sorted([e for e in events if e.date], key=lambda e: e.date)
    undated = [e for e in events if not e.date]
    return dated + undated

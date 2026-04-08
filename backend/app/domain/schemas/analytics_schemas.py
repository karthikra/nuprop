from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EngagementBreakdownResponse(BaseModel):
    opened_within_24h: int = 0
    time_on_site: int = 0
    sections_viewed: int = 0
    cards_expanded: int = 0
    investment_time: int = 0
    pdf_downloaded: int = 0
    return_visits: int = 0
    cta_clicked: int = 0
    total: int = 0
    classification: str = "cold"


class VisitorSummaryResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    fingerprint: str
    first_seen: datetime
    last_seen: datetime
    session_count: int
    total_time_seconds: int
    max_scroll_depth: int
    device_types: list[str] = []
    locations: list[str] = []
    engagement_score: int
    classification: str


class SectionHeatmapItem(BaseModel):
    section_id: str
    total_time_seconds: int
    unique_visitors: int
    avg_time_seconds: float


class ProposalAnalyticsResponse(BaseModel):
    proposal_id: UUID
    project_name: str
    client_name: str
    status: str
    total_views: int
    unique_visitors: int
    avg_time_seconds: float
    scroll_depth_distribution: dict[str, int]
    most_viewed_sections: list[SectionHeatmapItem]
    most_expanded_cards: list[dict]
    engagement_score: int
    engagement_breakdown: EngagementBreakdownResponse
    sent_at: datetime | None = None
    last_viewed_at: datetime | None = None


class ProposalAnalyticsListItem(BaseModel):
    proposal_id: UUID
    project_name: str
    client_name: str
    status: str
    engagement_score: int
    unique_visitors: int
    last_viewed_at: datetime | None = None
    sent_at: datetime | None = None


class OverviewStatsResponse(BaseModel):
    total_proposals: int
    proposals_sent: int
    proposals_viewed_today: int
    avg_engagement_score: float
    proposals_by_status: dict[str, int]
    win_rate: float | None = None
    recent_proposals: list[ProposalAnalyticsListItem] = []

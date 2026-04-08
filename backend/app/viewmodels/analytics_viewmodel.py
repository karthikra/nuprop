from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.analytics_schemas import (
    EngagementBreakdownResponse,
    OverviewStatsResponse,
    ProposalAnalyticsListItem,
    ProposalAnalyticsResponse,
    SectionHeatmapItem,
    VisitorSummaryResponse,
)
from app.infrastructure.db.models.client import Client
from app.infrastructure.db.models.proposal import Proposal
from app.infrastructure.db.models.base import IS_SQLITE
from app.infrastructure.db.repositories.analytics_repo import AnalyticsRepository
from app.services.engagement_scorer import compute_visitor_score, compute_proposal_score
from app.viewmodels.shared.viewmodel import ViewModelBase


def _id(val):
    return str(val) if IS_SQLITE else val


class AnalyticsViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._repo: AnalyticsRepository | None = None

    @property
    def repo(self) -> AnalyticsRepository:
        if not self._repo:
            self._repo = AnalyticsRepository(self._db)
        return self._repo

    async def get_overview(self, agency_id: UUID) -> OverviewStatsResponse:
        # Get all proposals for agency
        result = await self._db.execute(
            select(Proposal, Client.name)
            .join(Client, Proposal.client_id == Client.id)
            .where(Proposal.agency_id == _id(agency_id))
            .order_by(Proposal.updated_at.desc())
        )
        rows = list(result.all())

        total = len(rows)
        by_status: dict[str, int] = {}
        sent_count = 0
        won = 0
        lost = 0
        scores = []

        for prop, client_name in rows:
            st = prop.status or "draft"
            by_status[st] = by_status.get(st, 0) + 1
            if st in ("sent", "viewed", "won", "lost", "expired"):
                sent_count += 1
            if st == "won":
                won += 1
            if st == "lost":
                lost += 1
            scores.append(prop.engagement_score or 0)

        avg_score = sum(scores) / max(len(scores), 1)
        win_rate = won / (won + lost) if (won + lost) > 0 else None

        # Proposals viewed today
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        viewed_today = 0
        for prop, _ in rows:
            last_view = await self.repo.last_viewed_at(prop.id)
            if last_view:
                lv = last_view if last_view.tzinfo else last_view.replace(tzinfo=timezone.utc)
                if lv >= today_start:
                    viewed_today += 1

        # Recent proposals with analytics
        recent = []
        for prop, client_name in rows[:10]:
            visitors = await self.repo.count_visitors(prop.id)
            last_view = await self.repo.last_viewed_at(prop.id)
            recent.append(ProposalAnalyticsListItem(
                proposal_id=prop.id,
                project_name=prop.project_name,
                client_name=client_name,
                status=prop.status,
                engagement_score=prop.engagement_score or 0,
                unique_visitors=visitors,
                last_viewed_at=last_view,
                sent_at=prop.sent_at,
            ))

        return OverviewStatsResponse(
            total_proposals=total,
            proposals_sent=sent_count,
            proposals_viewed_today=viewed_today,
            avg_engagement_score=round(avg_score, 1),
            proposals_by_status=by_status,
            win_rate=round(win_rate, 2) if win_rate is not None else None,
            recent_proposals=recent,
        )

    async def get_proposal_analytics(self, proposal_id: UUID, agency_id: UUID) -> ProposalAnalyticsResponse | None:
        result = await self._db.execute(
            select(Proposal, Client.name)
            .join(Client, Proposal.client_id == Client.id)
            .where(Proposal.id == _id(proposal_id), Proposal.agency_id == _id(agency_id))
        )
        row = result.first()
        if not row:
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        prop, client_name = row

        visitors = await self.repo.get_visitors(proposal_id)
        total_views = await self.repo.count_page_views(proposal_id)
        scroll_dist = await self.repo.scroll_depth_distribution(proposal_id)
        section_stats = await self.repo.section_time_stats(proposal_id)
        card_stats = await self.repo.card_expand_counts(proposal_id)
        last_view = await self.repo.last_viewed_at(proposal_id)

        avg_time = sum(v.total_time_seconds for v in visitors) / max(len(visitors), 1)

        # Score the hottest visitor
        visitor_scores = []
        best_breakdown = EngagementBreakdownResponse()
        for v in visitors:
            events = await self.repo.get_events(proposal_id, v.id)
            event_dicts = [{"t": e.event_type, "section": e.section_id, "card": e.card_id, "duration": (e.data or {}).get("duration", 0), "cta": (e.data or {}).get("cta", "")} for e in events]
            score = compute_visitor_score(event_dicts, v.session_count, v.total_time_seconds, v.first_seen, prop.sent_at)
            visitor_scores.append(score)
            if score.total >= best_breakdown.total:
                best_breakdown = EngagementBreakdownResponse(**score.to_dict())

        proposal_score = compute_proposal_score(visitor_scores) if visitor_scores else 0

        return ProposalAnalyticsResponse(
            proposal_id=prop.id,
            project_name=prop.project_name,
            client_name=client_name,
            status=prop.status,
            total_views=total_views,
            unique_visitors=len(visitors),
            avg_time_seconds=round(avg_time, 1),
            scroll_depth_distribution=scroll_dist,
            most_viewed_sections=[SectionHeatmapItem(**s) for s in section_stats[:10]],
            most_expanded_cards=card_stats[:10],
            engagement_score=proposal_score,
            engagement_breakdown=best_breakdown,
            sent_at=prop.sent_at,
            last_viewed_at=last_view,
        )

    async def get_visitors(self, proposal_id: UUID, agency_id: UUID) -> list[VisitorSummaryResponse] | None:
        result = await self._db.execute(
            select(Proposal).where(Proposal.id == _id(proposal_id), Proposal.agency_id == _id(agency_id))
        )
        if not result.scalar_one_or_none():
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        visitors = await self.repo.get_visitors(proposal_id)
        return [VisitorSummaryResponse.model_validate(v) for v in visitors]

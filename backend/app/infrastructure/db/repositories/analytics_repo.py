from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.analytics_event import AnalyticsEvent
from app.infrastructure.db.models.base import IS_SQLITE
from app.infrastructure.db.models.visitor import Visitor


def _id(val: UUID | str) -> str:
    return str(val) if IS_SQLITE else val


def compute_fingerprint(ip: str, user_agent: str) -> str:
    raw = f"{ip}:{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class AnalyticsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Visitors ──────────────────────────────────────────────

    async def get_visitor(self, proposal_id: UUID | str, fingerprint: str) -> Visitor | None:
        result = await self.session.execute(
            select(Visitor).where(
                Visitor.proposal_id == _id(proposal_id),
                Visitor.fingerprint == fingerprint,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_visitor(
        self,
        proposal_id: UUID | str,
        fingerprint: str,
        ip_city: str | None = None,
        device_type: str | None = None,
    ) -> Visitor:
        visitor = await self.get_visitor(proposal_id, fingerprint)
        now = datetime.now(timezone.utc)

        if visitor:
            visitor.last_seen = now
            visitor.session_count += 1
            if device_type and device_type not in (visitor.device_types or []):
                devices = list(visitor.device_types or [])
                devices.append(device_type)
                visitor.device_types = devices
            if ip_city and ip_city not in (visitor.locations or []):
                locs = list(visitor.locations or [])
                locs.append(ip_city)
                visitor.locations = locs
            await self.session.flush()
            return visitor

        from app.infrastructure.db.models.base import _uuid_default
        visitor = Visitor(
            id=_uuid_default(),
            proposal_id=_id(proposal_id),
            fingerprint=fingerprint,
            first_seen=now,
            last_seen=now,
            session_count=1,
            total_time_seconds=0,
            max_scroll_depth=0,
            device_types=[device_type] if device_type else [],
            locations=[ip_city] if ip_city else [],
            engagement_score=0,
            classification="cold",
        )
        self.session.add(visitor)
        await self.session.flush()
        return visitor

    async def update_visitor_stats(
        self,
        visitor: Visitor,
        time_delta: int = 0,
        scroll_depth: int = 0,
    ):
        if time_delta > 0:
            visitor.total_time_seconds += time_delta
        if scroll_depth > visitor.max_scroll_depth:
            visitor.max_scroll_depth = scroll_depth
        await self.session.flush()

    async def update_visitor_score(self, visitor: Visitor, score: int, classification: str):
        visitor.engagement_score = score
        visitor.classification = classification
        await self.session.flush()

    async def get_visitors(self, proposal_id: UUID | str) -> list[Visitor]:
        result = await self.session.execute(
            select(Visitor)
            .where(Visitor.proposal_id == _id(proposal_id))
            .order_by(Visitor.last_seen.desc())
        )
        return list(result.scalars().all())

    async def count_visitors(self, proposal_id: UUID | str) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Visitor).where(Visitor.proposal_id == _id(proposal_id))
        )
        return result.scalar() or 0

    # ── Events ────────────────────────────────────────────────

    async def get_events(self, proposal_id: UUID | str, visitor_id: UUID | str | None = None) -> list[AnalyticsEvent]:
        stmt = select(AnalyticsEvent).where(AnalyticsEvent.proposal_id == _id(proposal_id))
        if visitor_id:
            stmt = stmt.where(AnalyticsEvent.visitor_id == _id(visitor_id))
        stmt = stmt.order_by(AnalyticsEvent.timestamp.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_page_views(self, proposal_id: UUID | str) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(AnalyticsEvent).where(
                AnalyticsEvent.proposal_id == _id(proposal_id),
                AnalyticsEvent.event_type == "page_view",
            )
        )
        return result.scalar() or 0

    async def section_time_stats(self, proposal_id: UUID | str) -> list[dict]:
        """Aggregate section_exit events for time-per-section."""
        result = await self.session.execute(
            select(AnalyticsEvent)
            .where(
                AnalyticsEvent.proposal_id == _id(proposal_id),
                AnalyticsEvent.event_type == "section_exit",
            )
        )
        events = result.scalars().all()

        sections: dict[str, dict] = {}
        visitors_per_section: dict[str, set] = {}
        for e in events:
            sid = e.section_id or "unknown"
            dur = (e.data or {}).get("duration", 0)
            if sid not in sections:
                sections[sid] = {"total_time": 0, "count": 0}
                visitors_per_section[sid] = set()
            sections[sid]["total_time"] += dur
            sections[sid]["count"] += 1
            if e.visitor_id:
                visitors_per_section[sid].add(str(e.visitor_id))

        return [
            {
                "section_id": sid,
                "total_time_seconds": data["total_time"],
                "unique_visitors": len(visitors_per_section.get(sid, set())),
                "avg_time_seconds": round(data["total_time"] / max(data["count"], 1), 1),
            }
            for sid, data in sorted(sections.items(), key=lambda x: x[1]["total_time"], reverse=True)
        ]

    async def card_expand_counts(self, proposal_id: UUID | str) -> list[dict]:
        result = await self.session.execute(
            select(AnalyticsEvent)
            .where(
                AnalyticsEvent.proposal_id == _id(proposal_id),
                AnalyticsEvent.event_type == "card_expand",
            )
        )
        events = result.scalars().all()

        cards: dict[str, int] = {}
        for e in events:
            cid = e.card_id or "unknown"
            cards[cid] = cards.get(cid, 0) + 1

        return [
            {"card_id": cid, "expand_count": count}
            for cid, count in sorted(cards.items(), key=lambda x: x[1], reverse=True)
        ]

    async def scroll_depth_distribution(self, proposal_id: UUID | str) -> dict[str, int]:
        result = await self.session.execute(
            select(AnalyticsEvent)
            .where(
                AnalyticsEvent.proposal_id == _id(proposal_id),
                AnalyticsEvent.event_type == "scroll_depth",
            )
        )
        events = result.scalars().all()

        depths = {"25": 0, "50": 0, "75": 0, "100": 0}
        for e in events:
            d = str((e.data or {}).get("depth", 0))
            if d in depths:
                depths[d] += 1
        return depths

    async def last_viewed_at(self, proposal_id: UUID | str) -> datetime | None:
        result = await self.session.execute(
            select(func.max(AnalyticsEvent.timestamp))
            .where(
                AnalyticsEvent.proposal_id == _id(proposal_id),
                AnalyticsEvent.event_type == "page_view",
            )
        )
        return result.scalar()

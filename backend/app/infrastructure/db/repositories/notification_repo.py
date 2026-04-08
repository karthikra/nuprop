from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.base import IS_SQLITE
from app.infrastructure.db.models.notification import Notification
from app.infrastructure.db.repositories.base import BaseRepository


def _id(val):
    return str(val) if IS_SQLITE else val


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Notification)

    async def list_for_agency(
        self,
        agency_id: UUID,
        skip: int = 0,
        limit: int = 20,
        unread_only: bool = False,
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.agency_id == _id(agency_id))
        if unread_only:
            stmt = stmt.where(Notification.read_at == None)  # noqa: E711
        stmt = stmt.order_by(Notification.sent_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_agency(self, agency_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Notification).where(Notification.agency_id == _id(agency_id))
        )
        return result.scalar() or 0

    async def unread_count(self, agency_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Notification).where(
                Notification.agency_id == _id(agency_id),
                Notification.read_at == None,  # noqa: E711
            )
        )
        return result.scalar() or 0

    async def mark_read(self, notification_id: UUID, agency_id: UUID) -> Notification | None:
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == _id(notification_id),
                Notification.agency_id == _id(agency_id),
            )
        )
        notif = result.scalar_one_or_none()
        if notif:
            notif.read_at = datetime.now(timezone.utc)
            await self.session.flush()
        return notif

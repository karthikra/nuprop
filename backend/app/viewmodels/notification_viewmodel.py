from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.notification_schemas import (
    NotificationListResponse,
    NotificationResponse,
)
from app.infrastructure.db.repositories.notification_repo import NotificationRepository
from app.viewmodels.shared.viewmodel import ViewModelBase


class NotificationViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._repo: NotificationRepository | None = None

    @property
    def repo(self) -> NotificationRepository:
        if not self._repo:
            self._repo = NotificationRepository(self._db)
        return self._repo

    async def list_notifications(
        self,
        agency_id: UUID,
        skip: int = 0,
        limit: int = 20,
        unread_only: bool = False,
    ) -> NotificationListResponse:
        items = await self.repo.list_for_agency(agency_id, skip, limit, unread_only)
        total = await self.repo.count_for_agency(agency_id)
        unread = await self.repo.unread_count(agency_id)
        return NotificationListResponse(
            items=[NotificationResponse.model_validate(n) for n in items],
            total=total,
            unread_count=unread,
        )

    async def get_unread_count(self, agency_id: UUID) -> int:
        return await self.repo.unread_count(agency_id)

    async def mark_as_read(self, notification_id: UUID, agency_id: UUID) -> NotificationResponse | None:
        notif = await self.repo.mark_read(notification_id, agency_id)
        if not notif:
            self.error = "Notification not found"
            self.status_code = 404
            return None
        return NotificationResponse.model_validate(notif)

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.base import IS_SQLITE
from app.infrastructure.db.models.rate_card import RateCard
from app.infrastructure.db.repositories.base import BaseRepository


def _id(val):
    return str(val) if IS_SQLITE else val


class RateCardRepository(BaseRepository[RateCard]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, RateCard)

    async def get_active(self, agency_id: UUID | str) -> RateCard | None:
        result = await self.session.execute(
            select(RateCard)
            .where(RateCard.agency_id == _id(agency_id), RateCard.is_active == True)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_versions(self, agency_id: UUID | str) -> list[RateCard]:
        result = await self.session.execute(
            select(RateCard)
            .where(RateCard.agency_id == _id(agency_id))
            .order_by(RateCard.created_at.desc())
        )
        return list(result.scalars().all())

    async def deactivate_all(self, agency_id: UUID | str) -> None:
        await self.session.execute(
            update(RateCard)
            .where(RateCard.agency_id == _id(agency_id))
            .values(is_active=False)
        )
        await self.session.flush()

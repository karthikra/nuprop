from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.repositories.base import BaseRepository


class AgencyRepository(BaseRepository[Agency]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Agency)

    async def get_by_slug(self, slug: str) -> Agency | None:
        result = await self.session.execute(
            select(Agency).where(Agency.slug == slug)
        )
        return result.scalar_one_or_none()

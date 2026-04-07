from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.client import Client
from app.infrastructure.db.repositories.base import BaseRepository


class ClientRepository(BaseRepository[Client]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Client)

    async def search(
        self,
        agency_id: UUID | str,
        query: str | None = None,
        industry: str | None = None,
        tag: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Client]:
        stmt = select(Client).where(Client.agency_id == str(agency_id))

        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Client.name.ilike(pattern),
                    Client.industry.ilike(pattern),
                    Client.notes.ilike(pattern),
                )
            )

        if industry:
            stmt = stmt.where(Client.industry == industry)

        stmt = stmt.order_by(Client.updated_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_slug(self, agency_id: UUID | str, slug: str) -> Client | None:
        result = await self.session.execute(
            select(Client).where(Client.agency_id == str(agency_id), Client.slug == slug)
        )
        return result.scalar_one_or_none()

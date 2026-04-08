from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.base import IS_SQLITE
from app.infrastructure.db.models.template import StrategyTemplate
from app.infrastructure.db.repositories.base import BaseRepository


def _id(val):
    return str(val) if IS_SQLITE else val


class TemplateRepository(BaseRepository[StrategyTemplate]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, StrategyTemplate)

    async def list_for_agency(self, agency_id: UUID | str) -> list[StrategyTemplate]:
        """List system templates + agency custom templates."""
        result = await self.session.execute(
            select(StrategyTemplate)
            .where(
                or_(
                    StrategyTemplate.is_system == True,
                    StrategyTemplate.agency_id == _id(agency_id),
                )
            )
            .order_by(StrategyTemplate.is_system.desc(), StrategyTemplate.name)
        )
        return list(result.scalars().all())

    async def get_by_key(self, template_key: str, agency_id: UUID | str | None = None) -> StrategyTemplate | None:
        stmt = select(StrategyTemplate).where(StrategyTemplate.template_key == template_key)
        if agency_id:
            stmt = stmt.where(
                or_(
                    StrategyTemplate.is_system == True,
                    StrategyTemplate.agency_id == _id(agency_id),
                )
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

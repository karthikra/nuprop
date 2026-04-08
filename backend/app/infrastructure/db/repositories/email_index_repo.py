from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.base import IS_SQLITE
from app.infrastructure.db.models.email_index import EmailIndex
from app.infrastructure.db.repositories.base import BaseRepository


def _id(val):
    return str(val) if IS_SQLITE else val


class EmailIndexRepository(BaseRepository[EmailIndex]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EmailIndex)

    async def get_by_message_id(self, gmail_message_id: str) -> EmailIndex | None:
        result = await self.session.execute(
            select(EmailIndex).where(EmailIndex.gmail_message_id == gmail_message_id)
        )
        return result.scalar_one_or_none()

    async def get_existing_message_ids(self, agency_id: UUID | str, message_ids: list[str]) -> set[str]:
        if not message_ids:
            return set()
        result = await self.session.execute(
            select(EmailIndex.gmail_message_id).where(
                EmailIndex.agency_id == _id(agency_id),
                EmailIndex.gmail_message_id.in_(message_ids),
            )
        )
        return {row[0] for row in result.all()}

    async def search_by_domain(
        self, agency_id: UUID | str, domain: str, limit: int = 50, offset: int = 0,
    ) -> list[EmailIndex]:
        result = await self.session.execute(
            select(EmailIndex)
            .where(EmailIndex.agency_id == _id(agency_id), EmailIndex.client_domain == domain)
            .order_by(EmailIndex.date.desc())
            .offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_for_domains(
        self, agency_id: UUID | str, domains: list[str], limit: int = 20,
    ) -> list[EmailIndex]:
        if not domains:
            return []
        result = await self.session.execute(
            select(EmailIndex)
            .where(EmailIndex.agency_id == _id(agency_id), EmailIndex.client_domain.in_(domains))
            .order_by(EmailIndex.date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_agency(self, agency_id: UUID | str) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(EmailIndex).where(EmailIndex.agency_id == _id(agency_id))
        )
        return result.scalar() or 0

    async def delete_by_agency(self, agency_id: UUID | str) -> int:
        result = await self.session.execute(
            delete(EmailIndex).where(EmailIndex.agency_id == _id(agency_id))
        )
        return result.rowcount

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.email_index import EmailIndex
from app.infrastructure.db.repositories.base import BaseRepository


def _id(val):
    # Schema stores IDs as VARCHAR(36) on both backends; always coerce.
    return str(val) if val is not None else None


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

    async def upsert_many(
        self, rows: list[EmailIndex], chunk_size: int = 50,
    ) -> int:
        """Persist a list of EmailIndex rows in chunks, committing each chunk.

        This bounds the rollback blast radius: a failure mid-way through one
        chunk loses at most `chunk_size` rows, while everything committed
        before is preserved. Caller is expected to have already filtered out
        duplicates (use `get_existing_message_ids` first).
        """
        if not rows:
            return 0
        written = 0
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            self.session.add_all(chunk)
            await self.session.commit()
            written += len(chunk)
        return written

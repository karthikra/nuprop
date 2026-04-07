from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.client import Client
from app.infrastructure.db.models.proposal import Proposal
from app.infrastructure.db.repositories.base import BaseRepository


class ProposalRepository(BaseRepository[Proposal]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Proposal)

    async def list_by_agency(
        self,
        agency_id: UUID | str,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[tuple[Proposal, str]]:
        stmt = (
            select(Proposal, Client.name)
            .join(Client, Proposal.client_id == Client.id)
            .where(Proposal.agency_id == str(agency_id))
        )
        if status:
            stmt = stmt.where(Proposal.status == status)
        stmt = stmt.order_by(Proposal.updated_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.all())

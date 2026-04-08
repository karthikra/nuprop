from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.rate_card_schemas import CreateVersionRequest, RateCardUpdate
from app.infrastructure.db.models.rate_card import RateCard
from app.infrastructure.db.repositories.rate_card_repo import RateCardRepository
from app.viewmodels.shared.viewmodel import ViewModelBase


class RateCardViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._repo: RateCardRepository | None = None

    @property
    def repo(self) -> RateCardRepository:
        if not self._repo:
            self._repo = RateCardRepository(self._db)
        return self._repo

    async def get_active(self, agency_id: UUID) -> RateCard | None:
        rc = await self.repo.get_active(agency_id)
        if not rc:
            self.error = "No active rate card"
            self.status_code = 404
        return rc

    async def list_versions(self, agency_id: UUID) -> list[RateCard]:
        return await self.repo.list_versions(agency_id)

    async def update_rate_card(self, rate_card_id: UUID, data: RateCardUpdate) -> RateCard | None:
        update_data = data.model_dump(exclude_unset=True)
        rc = await self.repo.update(rate_card_id, **update_data)
        if not rc:
            self.error = "Rate card not found"
            self.status_code = 404
        return rc

    async def create_version(self, agency_id: UUID, data: CreateVersionRequest) -> RateCard:
        current = await self.repo.get_active(agency_id)

        # Deactivate all existing versions
        await self.repo.deactivate_all(agency_id)

        # Clone from current or create empty
        new_rc = await self.repo.create(
            agency_id=agency_id,
            version=data.version,
            is_active=True,
            offerings=current.offerings if current else {},
            hourly_rates=current.hourly_rates if current else {},
            multipliers=current.multipliers if current else {},
            pass_through_markup=current.pass_through_markup if current else 0.10,
            standard_options=current.standard_options if current else 3,
            standard_revisions=current.standard_revisions if current else 2,
        )
        self.status_code = 201
        return new_rc

from __future__ import annotations

import json
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.agency_schemas import AgencyUpdate, OnboardingStepRequest
from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.models.rate_card import RateCard
from app.infrastructure.db.models.template import StrategyTemplate
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.base import BaseRepository
from app.viewmodels.shared.viewmodel import ViewModelBase


class AgencyViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._agency_repo: AgencyRepository | None = None

    @property
    def agency_repo(self) -> AgencyRepository:
        if not self._agency_repo:
            self._agency_repo = AgencyRepository(self._db)
        return self._agency_repo

    async def get_agency(self, agency_id: UUID) -> Agency | None:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
        return agency

    async def update_agency(self, agency_id: UUID, data: AgencyUpdate) -> Agency | None:
        update_data = data.model_dump(exclude_unset=True)
        agency = await self.agency_repo.update(agency_id, **update_data)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
        return agency

    async def process_onboarding_step(
        self, agency_id: UUID, step_data: OnboardingStepRequest
    ) -> Agency | None:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
            return None

        data = step_data.data

        if step_data.step == 1:
            # Profile: name, colours, fonts
            await self.agency_repo.update(
                agency_id,
                name=data.get("name", agency.name),
                colours=data.get("colours", agency.colours),
                fonts=data.get("fonts", agency.fonts),
                logo_url=data.get("logo_url"),
            )

        elif step_data.step == 2:
            # Rate card
            rate_card_repo = BaseRepository(self._db, RateCard)
            await rate_card_repo.create(
                agency_id=agency_id,
                version=data.get("version", "v1"),
                offerings=data.get("offerings", {}),
                hourly_rates=data.get("hourly_rates", {}),
                multipliers=data.get("multipliers", {}),
                pass_through_markup=data.get("pass_through_markup", 0.10),
                standard_options=data.get("standard_options", 3),
                standard_revisions=data.get("standard_revisions", 2),
            )

        elif step_data.step == 3:
            # Voice calibration
            await self.agency_repo.update(
                agency_id,
                voice_profile=data.get("voice_profile", ""),
            )

        elif step_data.step == 4:
            # Complete
            await self.agency_repo.update(agency_id, onboarding_complete=True)

        return await self.agency_repo.get_by_id(agency_id)

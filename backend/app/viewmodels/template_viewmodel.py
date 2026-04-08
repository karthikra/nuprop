from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.template_schemas import CloneTemplateRequest, TemplateCreate, TemplateUpdate
from app.infrastructure.db.models.template import StrategyTemplate
from app.infrastructure.db.repositories.template_repo import TemplateRepository
from app.viewmodels.shared.viewmodel import ViewModelBase


class TemplateViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._repo: TemplateRepository | None = None

    @property
    def repo(self) -> TemplateRepository:
        if not self._repo:
            self._repo = TemplateRepository(self._db)
        return self._repo

    async def list_templates(self, agency_id: UUID) -> list[StrategyTemplate]:
        return await self.repo.list_for_agency(agency_id)

    async def get_template(self, template_id: UUID, agency_id: UUID) -> StrategyTemplate | None:
        tmpl = await self.repo.get_by_id(template_id)
        if not tmpl:
            self.error = "Template not found"
            self.status_code = 404
            return None
        # Must be system or belong to this agency
        if not tmpl.is_system and str(tmpl.agency_id) != str(agency_id):
            self.error = "Template not found"
            self.status_code = 404
            return None
        return tmpl

    async def create_template(self, agency_id: UUID, data: TemplateCreate) -> StrategyTemplate:
        tmpl = await self.repo.create(
            agency_id=agency_id,
            template_key=data.template_key,
            name=data.name,
            description=data.description,
            category=data.category,
            config=data.config,
            is_system=False,
        )
        self.status_code = 201
        return tmpl

    async def update_template(self, template_id: UUID, agency_id: UUID, data: TemplateUpdate) -> StrategyTemplate | None:
        tmpl = await self.get_template(template_id, agency_id)
        if not tmpl:
            return None
        if tmpl.is_system:
            self.error = "Cannot edit system templates. Clone it first."
            self.status_code = 403
            return None
        update_data = data.model_dump(exclude_unset=True)
        return await self.repo.update(template_id, **update_data)

    async def delete_template(self, template_id: UUID, agency_id: UUID) -> bool:
        tmpl = await self.get_template(template_id, agency_id)
        if not tmpl:
            return False
        if tmpl.is_system:
            self.error = "Cannot delete system templates"
            self.status_code = 403
            return False
        return await self.repo.delete(template_id)

    async def clone_template(self, template_id: UUID, agency_id: UUID, data: CloneTemplateRequest) -> StrategyTemplate | None:
        source = await self.get_template(template_id, agency_id)
        if not source:
            return None
        clone = await self.repo.create(
            agency_id=agency_id,
            template_key=data.new_key,
            name=data.new_name,
            description=source.description,
            category=source.category,
            config=source.config,
            is_system=False,
        )
        self.status_code = 201
        return clone

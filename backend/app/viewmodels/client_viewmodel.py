from __future__ import annotations

import re
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.client_schemas import ClientCreate, ClientUpdate
from app.infrastructure.db.models.client import Client
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.viewmodels.shared.viewmodel import ViewModelBase


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower().strip())
    return re.sub(r"[-\s]+", "-", slug)


class ClientViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._repo: ClientRepository | None = None

    @property
    def repo(self) -> ClientRepository:
        if not self._repo:
            self._repo = ClientRepository(self._db)
        return self._repo

    async def list_clients(
        self,
        agency_id: UUID,
        query: str | None = None,
        industry: str | None = None,
        tag: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Client]:
        return await self.repo.search(agency_id, query, industry, tag, skip, limit)

    async def get_client(self, client_id: UUID) -> Client | None:
        client = await self.repo.get_by_id(client_id)
        if not client:
            self.error = "Client not found"
            self.status_code = 404
        return client

    async def create_client(self, agency_id: UUID, data: ClientCreate) -> Client:
        client = await self.repo.create(
            agency_id=agency_id,
            name=data.name,
            slug=_slugify(data.name),
            industry=data.industry,
            size=data.size,
            contacts=[c.model_dump() for c in data.contacts],
            notes=data.notes,
            tags=data.tags,
        )
        self.status_code = 201
        return client

    async def update_client(self, client_id: UUID, data: ClientUpdate) -> Client | None:
        update_data = data.model_dump(exclude_unset=True)
        if "contacts" in update_data and update_data["contacts"] is not None:
            update_data["contacts"] = [c if isinstance(c, dict) else c.model_dump() for c in update_data["contacts"]]
        if "name" in update_data:
            update_data["slug"] = _slugify(update_data["name"])
        client = await self.repo.update(client_id, **update_data)
        if not client:
            self.error = "Client not found"
            self.status_code = 404
        return client

    async def delete_client(self, client_id: UUID) -> bool:
        deleted = await self.repo.delete(client_id)
        if not deleted:
            self.error = "Client not found"
            self.status_code = 404
        return deleted

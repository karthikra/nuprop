from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.base import IS_SQLITE, BaseModel

T = TypeVar("T", bound=BaseModel)


def _coerce_id(id: UUID) -> str | UUID:
    """SQLite stores UUIDs as strings; PostgreSQL uses native UUID."""
    return str(id) if IS_SQLITE else id


class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: UUID) -> T | None:
        result = await self.session.execute(select(self.model).where(self.model.id == _coerce_id(id)))
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        **filters: object,
    ) -> list[T]:
        query = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                query = query.where(getattr(self.model, key) == value)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **data: object) -> T:
        if IS_SQLITE:
            from uuid import UUID as _UUID
            data = {k: str(v) if isinstance(v, _UUID) else v for k, v in data.items()}
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: UUID, **data: object) -> T | None:
        data = {k: v for k, v in data.items() if v is not None}
        if not data:
            return await self.get_by_id(id)
        await self.session.execute(
            update(self.model).where(self.model.id == _coerce_id(id)).values(**data)
        )
        return await self.get_by_id(id)

    async def delete(self, id: UUID) -> bool:
        result = await self.session.execute(
            delete(self.model).where(self.model.id == _coerce_id(id))
        )
        return result.rowcount > 0

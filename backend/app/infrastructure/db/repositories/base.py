from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.base import BaseModel

T = TypeVar("T", bound=BaseModel)


def _coerce_id(id: UUID | str) -> str:
    """Schema stores IDs as VARCHAR(36) on both SQLite and Postgres.

    Passing a Python ``UUID`` object to asyncpg triggers a UUID parameter bind
    which Postgres then can't compare against a VARCHAR column (``operator does
    not exist: character varying = uuid``). Always coerce to ``str``.
    """
    return str(id) if isinstance(id, UUID) else id


def _coerce_uuid_values(data: dict) -> dict:
    """Coerce any UUID values in ``data`` to strings — schema is VARCHAR(36)."""
    return {k: str(v) if isinstance(v, UUID) else v for k, v in data.items()}


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
                if isinstance(value, UUID):
                    value = str(value)
                query = query.where(getattr(self.model, key) == value)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **data: object) -> T:
        data = _coerce_uuid_values(data)
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: UUID, **data: object) -> T | None:
        # Write exactly what the caller passes. Callers that only want to
        # update a subset use ``model_dump(exclude_unset=True)``, so absent
        # fields are never in ``data``; an explicit ``None`` here means
        # "clear this column" and is honoured.
        if not data:
            return await self.get_by_id(id)
        data = _coerce_uuid_values(data)
        await self.session.execute(
            update(self.model).where(self.model.id == _coerce_id(id)).values(**data)
        )
        return await self.get_by_id(id)

    async def delete(self, id: UUID) -> bool:
        result = await self.session.execute(
            delete(self.model).where(self.model.id == _coerce_id(id))
        )
        return result.rowcount > 0

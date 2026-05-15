from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.infrastructure.db.database import Base

_settings = get_settings()
_is_sqlite = _settings.DATABASE_URL.startswith("sqlite")

# UUID column type: String(36) on both Postgres and SQLite.
# The Alembic initial migration created every ID/FK column as VARCHAR(36), so
# the model must match. A previous attempt to use native PG_UUID on Postgres
# silently produced a schema-vs-model type mismatch that crashed every query
# against a real Postgres database (operator does not exist: varchar = uuid).
_uuid_col = String(36)


def _uuid_default():
    """Generate a UUID as a string — schema is VARCHAR(36) on both backends."""
    return str(uuid4())


def uuid_pk():
    """Primary key column that works on both SQLite and PostgreSQL."""
    return mapped_column(_uuid_col, primary_key=True, default=_uuid_default)


def uuid_fk(fk_target: str, nullable: bool = False, **kwargs):
    """Foreign key column that works on both SQLite and PostgreSQL."""
    from sqlalchemy import ForeignKey
    return mapped_column(
        _uuid_col, ForeignKey(fk_target, **kwargs), nullable=nullable,
    )


# JSON column: native JSONB on Postgres, JSON on SQLite
if _is_sqlite:
    from sqlalchemy import JSON as JSONColumn
else:
    from sqlalchemy.dialects.postgresql import JSONB as JSONColumn  # type: ignore[assignment]


IS_SQLITE = _is_sqlite


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BaseModel(Base, TimestampMixin):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        _uuid_col,
        primary_key=True,
        default=_uuid_default,
    )

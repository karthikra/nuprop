from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class StrategyTemplate(BaseModel):
    __tablename__ = "strategy_templates"

    agency_id: Mapped[UUID | None] = uuid_fk("agencies.id", ondelete="CASCADE", nullable=True)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    agency = relationship("Agency", back_populates="templates")

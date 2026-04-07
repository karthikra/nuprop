from __future__ import annotations

from uuid import UUID

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class Client(BaseModel):
    __tablename__ = "clients"

    agency_id: Mapped[UUID] = uuid_fk("agencies.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[str | None] = mapped_column(String(50))
    contacts: Mapped[dict] = mapped_column(JSONColumn, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[dict] = mapped_column(JSONColumn, default=list)
    context_profile: Mapped[dict] = mapped_column(JSONColumn, default=dict)

    agency = relationship("Agency", back_populates="clients")
    proposals = relationship("Proposal", back_populates="client", cascade="all, delete-orphan")

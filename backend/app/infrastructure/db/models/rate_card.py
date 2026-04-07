from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class RateCard(BaseModel):
    __tablename__ = "rate_cards"

    agency_id: Mapped[UUID] = uuid_fk("agencies.id", ondelete="CASCADE")
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    offerings: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    hourly_rates: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    multipliers: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    pass_through_markup: Mapped[float] = mapped_column(Float, default=0.10)
    standard_options: Mapped[int] = mapped_column(Integer, default=3)
    standard_revisions: Mapped[int] = mapped_column(Integer, default=2)

    agency = relationship("Agency", back_populates="rate_cards")

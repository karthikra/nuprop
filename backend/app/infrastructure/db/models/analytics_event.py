from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class AnalyticsEvent(BaseModel):
    __tablename__ = "analytics_events"

    proposal_id: Mapped[UUID] = uuid_fk("proposals.id", ondelete="CASCADE")
    visitor_id: Mapped[UUID | None] = uuid_fk("visitors.id", ondelete="SET NULL", nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    section_id: Mapped[str | None] = mapped_column(String(50))
    card_id: Mapped[str | None] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(50))
    ip_city: Mapped[str | None] = mapped_column(String(100))

    proposal = relationship("Proposal", back_populates="analytics_events")

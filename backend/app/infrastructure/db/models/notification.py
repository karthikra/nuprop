from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class Notification(BaseModel):
    __tablename__ = "notifications"

    proposal_id: Mapped[UUID] = uuid_fk("proposals.id", ondelete="CASCADE")
    agency_id: Mapped[UUID] = uuid_fk("agencies.id", ondelete="CASCADE")
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), default="normal")
    channels_sent: Mapped[dict] = mapped_column(JSONColumn, default=list)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    proposal = relationship("Proposal", back_populates="notifications")
    agency = relationship("Agency", back_populates="notifications")

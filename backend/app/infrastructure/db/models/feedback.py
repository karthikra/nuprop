from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, uuid_fk


class Feedback(BaseModel):
    __tablename__ = "feedback"

    proposal_id: Mapped[UUID] = uuid_fk("proposals.id", ondelete="CASCADE")
    visitor_fingerprint: Mapped[str] = mapped_column(String(24), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    proposal = relationship("Proposal", back_populates="feedback")

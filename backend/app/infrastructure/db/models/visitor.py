from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class Visitor(BaseModel):
    __tablename__ = "visitors"

    proposal_id: Mapped[UUID] = uuid_fk("proposals.id", ondelete="CASCADE")
    fingerprint: Mapped[str] = mapped_column(String(24), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, default=1)
    total_time_seconds: Mapped[int] = mapped_column(Integer, default=0)
    max_scroll_depth: Mapped[int] = mapped_column(Integer, default=0)
    device_types: Mapped[dict] = mapped_column(JSONColumn, default=list)
    locations: Mapped[dict] = mapped_column(JSONColumn, default=list)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0)
    classification: Mapped[str] = mapped_column(String(20), default="cold")

    proposal = relationship("Proposal", back_populates="visitors")

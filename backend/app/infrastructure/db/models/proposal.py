from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class ProposalStatus(str, enum.Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    REVIEW = "review"
    SENT = "sent"
    VIEWED = "viewed"
    WON = "won"
    LOST = "lost"
    EXPIRED = "expired"


class Proposal(BaseModel):
    __tablename__ = "proposals"

    agency_id: Mapped[UUID] = uuid_fk("agencies.id", ondelete="CASCADE")
    client_id: Mapped[UUID] = uuid_fk("clients.id", ondelete="CASCADE")
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=ProposalStatus.DRAFT.value)
    brief: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    template_id: Mapped[str | None] = mapped_column(String(100))
    preferences: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    research: Mapped[str | None] = mapped_column(Text)
    benchmarks: Mapped[str | None] = mapped_column(Text)
    context_brief: Mapped[str | None] = mapped_column(Text)
    cost_model: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    site_url: Mapped[str | None] = mapped_column(String(500))
    docx_path: Mapped[str | None] = mapped_column(String(500))
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engagement_score: Mapped[int] = mapped_column(Integer, default=0)
    pipeline_state: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    rate_card_gaps: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    rate_card_override: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)

    # Section columns — each carries the full {content, assets, included, metadata}
    # payload; NULL means "section not yet generated"; included=false means
    # the user toggled it off. Canonical order lives in
    # app/services/sections/__init__.py::SECTION_ORDER.
    cover_page:           Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    executive_summary:    Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    problem_statement:    Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    proposed_solution:    Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    scope_of_work:        Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    timeline:             Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    pricing:              Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    qualifications:       Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    terms_and_conditions: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)

    agency = relationship("Agency", back_populates="proposals")
    client = relationship("Client", back_populates="proposals")
    chat_messages = relationship("ChatMessage", back_populates="proposal", cascade="all, delete-orphan")
    visitors = relationship("Visitor", back_populates="proposal", cascade="all, delete-orphan")
    analytics_events = relationship("AnalyticsEvent", back_populates="proposal", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="proposal", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="proposal", cascade="all, delete-orphan")

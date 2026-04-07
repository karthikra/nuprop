from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class EmailIndex(BaseModel):
    __tablename__ = "email_index"

    agency_id: Mapped[UUID] = uuid_fk("agencies.id", ondelete="CASCADE")
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    client_name: Mapped[str | None] = mapped_column(String(255))
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    to_addresses: Mapped[dict] = mapped_column(JSONColumn, default=list)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    # embedding: pgvector column added via migration on PostgreSQL only
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

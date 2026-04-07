from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn, uuid_fk


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(str, enum.Enum):
    TEXT = "text"
    BRIEF_SUMMARY = "brief_summary"
    RESEARCH_FINDINGS = "research_findings"
    BENCHMARK_DATA = "benchmark_data"
    COST_MODEL = "cost_model"
    NARRATIVE_PREVIEW = "narrative_preview"
    APPROVAL_GATE = "approval_gate"
    PROGRESS_UPDATE = "progress_update"
    FILE_UPLOAD = "file_upload"
    OUTPUT_READY = "output_ready"
    ERROR = "error"


class ChatMessage(BaseModel):
    __tablename__ = "chat_messages"

    proposal_id: Mapped[UUID] = uuid_fk("proposals.id", ondelete="CASCADE")
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), default=MessageType.TEXT.value)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    phase: Mapped[str | None] = mapped_column(String(50))

    proposal = relationship("Proposal", back_populates="chat_messages")

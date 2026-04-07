from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SendMessageRequest(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    proposal_id: UUID
    role: str
    message_type: str
    content: str
    extra_data: dict
    phase: str | None = None
    created_at: datetime


class WSMessage(BaseModel):
    type: str
    message: ChatMessageResponse | None = None
    phase: str | None = None
    error: str | None = None

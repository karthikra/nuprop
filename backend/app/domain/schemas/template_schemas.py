from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TemplateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    template_key: str
    name: str
    description: str | None = None
    category: str
    config: dict
    is_system: bool
    created_at: datetime


class TemplateCreate(BaseModel):
    template_key: str
    name: str
    description: str | None = None
    category: str
    config: dict = {}


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    config: dict | None = None


class CloneTemplateRequest(BaseModel):
    new_key: str
    new_name: str

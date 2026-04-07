from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ContactInfo(BaseModel):
    name: str
    role: str | None = None
    email: str | None = None
    phone: str | None = None


class ClientCreate(BaseModel):
    name: str
    industry: str | None = None
    size: str | None = None
    contacts: list[ContactInfo] = []
    notes: str | None = None
    tags: list[str] = []


class ClientUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    size: str | None = None
    contacts: list[ContactInfo] | None = None
    notes: str | None = None
    tags: list[str] | None = None


class ClientResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    name: str
    slug: str
    industry: str | None = None
    size: str | None = None
    contacts: list[dict] = []
    notes: str | None = None
    tags: list[str] = []
    context_profile: dict = {}
    created_at: datetime
    updated_at: datetime

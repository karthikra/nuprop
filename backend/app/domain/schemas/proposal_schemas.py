from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProposalCreate(BaseModel):
    client_id: UUID
    project_name: str


class ProposalUpdate(BaseModel):
    project_name: str | None = None
    status: str | None = None
    brief: dict | None = None
    template_id: str | None = None
    preferences: dict | None = None


class ProposalListItem(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    client_id: UUID
    client_name: str
    project_name: str
    status: str
    pipeline_state: dict
    created_at: datetime
    updated_at: datetime


class ProposalResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    agency_id: UUID
    client_id: UUID
    project_name: str
    status: str
    brief: dict
    template_id: str | None = None
    preferences: dict
    pipeline_state: dict
    created_at: datetime
    updated_at: datetime

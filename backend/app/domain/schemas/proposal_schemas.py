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


class PreferencesUpdate(BaseModel):
    letter_strategy: str | None = None
    letter_opening: str | None = None
    letter_length: str | None = None
    letter_custom_instructions: str | None = None
    pricing_model: str | None = None
    discount_tags: list[str] | None = None
    payment_terms: str | None = None
    scope_detail_level: str | None = None
    site_theme: str | None = None
    primary_format: str | None = None


# Maps preference keys to the pipeline phase they affect
PREF_PHASE_MAP: dict[str, str] = {
    "letter_strategy": "narrative_review",
    "letter_opening": "narrative_review",
    "letter_length": "narrative_review",
    "letter_custom_instructions": "narrative_review",
    "pricing_model": "cost_model_review",
    "discount_tags": "cost_model_review",
    "payment_terms": "narrative_review",
    "scope_detail_level": "narrative_review",
    "site_theme": "output_generation",
    "primary_format": "output_generation",
}


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

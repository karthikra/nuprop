from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RateCardResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    version: str
    is_active: bool
    offerings: dict
    hourly_rates: dict
    multipliers: dict
    pass_through_markup: float
    standard_options: int
    standard_revisions: int
    created_at: datetime
    updated_at: datetime


class RateCardSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    version: str
    is_active: bool
    created_at: datetime


class RateCardUpdate(BaseModel):
    offerings: dict | None = None
    hourly_rates: dict | None = None
    multipliers: dict | None = None
    pass_through_markup: float | None = None
    standard_options: int | None = None
    standard_revisions: int | None = None


class CreateVersionRequest(BaseModel):
    version: str

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class AgencyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    name: str
    slug: str
    logo_url: str | None = None
    colours: dict = {}
    fonts: dict = {}
    currency: str = "INR"
    gst_rate: float = 0.18
    payment_terms: dict = {}
    onboarding_complete: bool = False


class AgencyUpdate(BaseModel):
    name: str | None = None
    logo_url: str | None = None
    colours: dict | None = None
    fonts: dict | None = None
    voice_profile: str | None = None
    default_terms: str | None = None
    currency: str | None = None
    gst_rate: float | None = None
    payment_terms: dict | None = None
    settings: dict | None = None


class OnboardingStepRequest(BaseModel):
    step: int
    data: dict

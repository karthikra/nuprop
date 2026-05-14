"""Unit tests for Pydantic request/response schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.schemas.auth_schemas import RegisterRequest
from app.domain.schemas.client_schemas import ClientCreate
from app.domain.schemas.proposal_schemas import (
    PREF_PHASE_MAP,
    PreferencesUpdate,
    ProposalCreate,
)


def test_register_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="x", full_name="A", agency_name="B")


def test_register_request_accepts_valid_email():
    req = RegisterRequest(email="a@b.com", password="x", full_name="A", agency_name="B")
    assert req.email == "a@b.com"


def test_proposal_create_rejects_non_uuid_client_id():
    with pytest.raises(ValidationError):
        ProposalCreate(client_id="not-a-uuid", project_name="X")


def test_client_create_defaults_optional_fields():
    c = ClientCreate(name="Acme")
    assert c.contacts == []
    assert c.tags == []
    assert c.industry is None


def test_preferences_update_exclude_unset_only_emits_provided_fields():
    p = PreferencesUpdate(letter_strategy="warm")
    assert p.model_dump(exclude_unset=True) == {"letter_strategy": "warm"}


def test_pref_phase_map_covers_every_preference_field():
    """Every PreferencesUpdate field must map to a pipeline phase for staleness."""
    assert set(PreferencesUpdate.model_fields) == set(PREF_PHASE_MAP)

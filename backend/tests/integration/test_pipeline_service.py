"""Integration tests for PipelineService — each phase against a real session."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.pipeline_service import PipelineService


async def _make_proposal(db, *, brief=None, pipeline_state=None):
    agency = await AgencyRepository(db).create(name="PS Agency", slug="ps-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id,
        client_id=client.id,
        project_name="PS Project",
        brief=brief or {},
        pipeline_state=pipeline_state or {"current_phase": "brief", "phases_completed": []},
    )
    await db.commit()
    return agency, client, proposal


def test_merge_preferences_into_config_overlays_user_prefs():
    merged = PipelineService._merge_preferences_into_config(
        {"narrative": {"letter_strategy": "vision"}},
        {"letter_strategy": "warm", "site_theme": "dark"},
    )
    assert merged["narrative"]["letter_strategy"] == "warm"
    assert merged["output"]["site_theme"] == "dark"

"""Integration tests for the repository layer against a real (SQLite) database."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.infrastructure.db.models.base import IS_SQLITE
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.base import _coerce_id
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.notification_repo import NotificationRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.db.repositories.rate_card_repo import RateCardRepository
from app.infrastructure.db.repositories.template_repo import TemplateRepository
from app.infrastructure.db.repositories.user_repo import UserRepository


async def _make_agency(db, name="Repo Agency", slug=None):
    repo = AgencyRepository(db)
    agency = await repo.create(name=name, slug=slug or name.lower().replace(" ", "-"))
    await db.commit()
    return agency


# ── BaseRepository CRUD ──────────────────────────────────────────────────────
async def test_create_and_get_by_id(db):
    agency = await _make_agency(db)
    fetched = await AgencyRepository(db).get_by_id(agency.id)
    assert fetched is not None
    assert fetched.name == "Repo Agency"


async def test_get_by_id_missing_returns_none(db):
    assert await AgencyRepository(db).get_by_id(uuid.uuid4()) is None


async def test_get_all_with_filters(db):
    repo = AgencyRepository(db)
    await repo.create(name="Filterable", slug="filterable")
    await repo.create(name="Other", slug="other")
    await db.commit()
    results = await repo.get_all(name="Filterable")
    assert [a.name for a in results] == ["Filterable"]


async def test_update_changes_fields(db):
    agency = await _make_agency(db)
    updated = await AgencyRepository(db).update(agency.id, name="Renamed Agency")
    assert updated.name == "Renamed Agency"


async def test_update_with_no_data_is_a_noop_fetch(db):
    agency = await _make_agency(db)
    result = await AgencyRepository(db).update(agency.id)
    assert result.id == agency.id


async def test_update_can_clear_a_nullable_field_to_none(db):
    """Regression test for the BaseRepository.update() None-drop fix."""
    agency = await _make_agency(db)
    repo = AgencyRepository(db)
    await repo.update(agency.id, logo_url="https://cdn.test/logo.png")
    await db.commit()
    assert (await repo.get_by_id(agency.id)).logo_url == "https://cdn.test/logo.png"

    await repo.update(agency.id, logo_url=None)
    await db.commit()
    assert (await repo.get_by_id(agency.id)).logo_url is None


async def test_delete_removes_row(db):
    agency = await _make_agency(db)
    repo = AgencyRepository(db)
    assert await repo.delete(agency.id) is True
    assert await repo.get_by_id(agency.id) is None


async def test_delete_missing_returns_false(db):
    assert await AgencyRepository(db).delete(uuid.uuid4()) is False


def test_coerce_id_stringifies_on_sqlite():
    u = uuid.uuid4()
    coerced = _coerce_id(u)
    if IS_SQLITE:
        assert coerced == str(u)
    else:
        assert coerced == u


# ── specialised repository queries ───────────────────────────────────────────
async def test_user_repo_get_by_email(db):
    agency = await _make_agency(db)
    repo = UserRepository(db)
    await repo.create(
        agency_id=agency.id, email="findme@findme.example.com", hashed_password="x",
        full_name="Find Me",
    )
    await db.commit()
    found = await repo.get_by_email("findme@findme.example.com")
    assert found is not None
    assert found.full_name == "Find Me"
    assert await repo.get_by_email("nobody@nobody.example.com") is None


async def test_agency_repo_get_by_slug(db):
    await _make_agency(db, name="Slugged", slug="slugged-co")
    repo = AgencyRepository(db)
    assert (await repo.get_by_slug("slugged-co")).name == "Slugged"
    assert await repo.get_by_slug("does-not-exist") is None


async def test_client_repo_search_by_name_and_industry(db):
    agency = await _make_agency(db)
    repo = ClientRepository(db)
    await repo.create(agency_id=agency.id, name="Northwind", slug="northwind", industry="logistics")
    await repo.create(agency_id=agency.id, name="Southside", slug="southside", industry="hospitality")
    await db.commit()

    by_name = await repo.search(agency.id, query="north")
    assert [c.name for c in by_name] == ["Northwind"]

    by_industry = await repo.search(agency.id, industry="hospitality")
    assert [c.name for c in by_industry] == ["Southside"]


async def test_rate_card_repo_active_and_deactivate(db):
    agency = await _make_agency(db)
    repo = RateCardRepository(db)
    await repo.create(agency_id=agency.id, version="v1", is_active=True)
    await db.commit()
    assert (await repo.get_active(agency.id)).version == "v1"

    await repo.deactivate_all(agency.id)
    await db.commit()
    assert await repo.get_active(agency.id) is None


async def test_template_repo_list_and_get_by_key(db):
    agency = await _make_agency(db)
    repo = TemplateRepository(db)
    await repo.create(
        template_key="sys_t", name="System T", category="brand", is_system=True, agency_id=None
    )
    await repo.create(
        template_key="custom_t", name="Custom T", category="brand", is_system=False,
        agency_id=agency.id,
    )
    await db.commit()

    listed = await repo.list_for_agency(agency.id)
    assert {t.template_key for t in listed} == {"sys_t", "custom_t"}

    assert (await repo.get_by_key("sys_t")).name == "System T"
    assert await repo.get_by_key("missing") is None


async def test_chat_message_repo_orders_by_created_at(db):
    agency = await _make_agency(db)
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="P"
    )
    await db.commit()

    msg_repo = ChatMessageRepository(db)
    # explicit timestamps — SQLite CURRENT_TIMESTAMP only has 1-second resolution
    await msg_repo.create(
        proposal_id=proposal.id, role="user", content="first",
        created_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    await msg_repo.create(
        proposal_id=proposal.id, role="assistant", content="second",
        created_at=datetime(2025, 1, 1, 10, 0, 5, tzinfo=timezone.utc),
    )
    await db.commit()

    msgs = await msg_repo.list_by_proposal(proposal.id)
    assert [m.content for m in msgs] == ["first", "second"]


async def test_proposal_repo_list_by_agency_joins_client_name(db):
    agency = await _make_agency(db)
    client = await ClientRepository(db).create(
        agency_id=agency.id, name="Joined Client", slug="joined"
    )
    await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="P1"
    )
    await db.commit()

    rows = await ProposalRepository(db).list_by_agency(agency.id)
    assert len(rows) == 1
    _proposal, client_name = rows[0]
    assert client_name == "Joined Client"


async def test_notification_repo_counts_and_mark_read(db):
    agency = await _make_agency(db)
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="P"
    )
    await db.commit()

    repo = NotificationRepository(db)
    await repo.create(
        proposal_id=proposal.id, agency_id=agency.id, alert_type="first_view",
        message="m1", sent_at=datetime.now(timezone.utc),
    )
    await repo.create(
        proposal_id=proposal.id, agency_id=agency.id, alert_type="cta_click",
        message="m2", sent_at=datetime.now(timezone.utc),
    )
    await db.commit()

    assert await repo.count_for_agency(agency.id) == 2
    assert await repo.unread_count(agency.id) == 2

    notifs = await repo.list_for_agency(agency.id)
    await repo.mark_read(notifs[0].id, agency.id)
    await db.commit()
    assert await repo.unread_count(agency.id) == 1

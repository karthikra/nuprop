"""Integration tests for the ideation side-channel.

Repo-level tests live here too because the channel filter is what backs the
ideation API; one file per feature keeps the test surface easy to find.
"""

from __future__ import annotations

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository


async def _make_proposal(db):
    agency = await AgencyRepository(db).create(name="ID Agency", slug="id-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="P",
        brief={}, pipeline_state={"current_phase": "brief", "phases_completed": []},
    )
    await db.commit()
    return proposal


async def test_list_by_proposal_filters_by_channel(db):
    proposal = await _make_proposal(db)
    msg_repo = ChatMessageRepository(db)

    await msg_repo.create(
        proposal_id=proposal.id, role="user", message_type="text",
        content="main msg", phase="brief", channel="main",
    )
    await msg_repo.create(
        proposal_id=proposal.id, role="user", message_type="text",
        content="ideation msg", phase="ideation", channel="ideation",
    )
    await db.commit()

    main = await msg_repo.list_by_proposal(proposal.id)
    ideation = await msg_repo.list_by_proposal(proposal.id, channel="ideation")

    assert [m.content for m in main] == ["main msg"]
    assert [m.content for m in ideation] == ["ideation msg"]

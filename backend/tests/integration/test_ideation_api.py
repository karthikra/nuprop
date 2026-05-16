"""Integration tests for the ideation side-channel.

Repo-level tests live here too because the channel filter is what backs the
ideation API; one file per feature keeps the test surface easy to find.
"""

from __future__ import annotations

from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository


async def test_list_by_proposal_filters_by_channel(db, make_proposal_db):
    _, _, proposal = await make_proposal_db()
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


async def test_get_ideation_messages_returns_empty_for_new_proposal(client, registered, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    resp = await client.get(
        f"/api/v1/chat/{p['id']}/ideation/messages",
        headers=registered.headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_ideation_messages_cross_agency_returns_404(client, registered, second_agency, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    resp = await client.get(
        f"/api/v1/chat/{p['id']}/ideation/messages",
        headers=second_agency.headers,
    )
    assert resp.status_code == 404


async def test_send_ideation_cross_agency_returns_404(client, registered, second_agency, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    resp = await client.post(
        f"/api/v1/chat/{p['id']}/ideation/send",
        headers=second_agency.headers,
        json={"content": "should not work"},
    )
    assert resp.status_code == 404


async def test_send_ideation_enqueues_and_returns_only_the_user_message(
    client, registered, arq_pool, make_proposal_api,
):
    p = await make_proposal_api(client, registered.headers)
    resp = await client.post(
        f"/api/v1/chat/{p['id']}/ideation/send",
        headers=registered.headers,
        json={"content": "What if we positioned this as a retainer?"},
    )
    assert resp.status_code == 201
    msgs = resp.json()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["channel"] == "ideation"
    assert msgs[0]["content"].startswith("What if")

    arq_pool.enqueue_job.assert_awaited()
    job_name = arq_pool.enqueue_job.await_args.args[0]
    assert job_name == "run_ideation"


async def test_ideation_thread_is_separate_from_the_main_thread(
    client, registered, arq_pool, make_proposal_api,
):
    """Posting on the ideation channel must NOT pollute the main thread."""
    p = await make_proposal_api(client, registered.headers)

    await client.post(
        f"/api/v1/chat/{p['id']}/ideation/send",
        headers=registered.headers,
        json={"content": "ideation only"},
    )

    main = (await client.get(
        f"/api/v1/chat/{p['id']}/messages",
        headers=registered.headers,
    )).json()
    assert main == []

    ideation = (await client.get(
        f"/api/v1/chat/{p['id']}/ideation/messages",
        headers=registered.headers,
    )).json()
    assert len(ideation) == 1
    assert ideation[0]["channel"] == "ideation"

"""Integration tests for the chat API — messages, send, approval gates,
and the cost-model line-item patch.

After the background-worker refactor, brief-phase send_message and the
non-brief approval gates enqueue ARQ jobs instead of running the pipeline
inline. Tests that exercise those paths require the ``arq_pool`` fixture and
assert the enqueue rather than inline pipeline output.
"""

from __future__ import annotations

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from tests.conftest import API


async def test_get_messages_empty(client, registered, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    resp = await client.get(f"{API}/chat/{p['id']}/messages", headers=registered.headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_messages_cross_agency_404(client, registered, second_agency, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    resp = await client.get(f"{API}/chat/{p['id']}/messages", headers=second_agency.headers)
    assert resp.status_code == 404


async def test_send_message_brief_phase_enqueues_analyze_brief(client, registered, arq_pool, make_proposal_api):
    """In the brief phase, send_message persists the user message and enqueues
    the analyze_brief job — it does not run the analyzer inline. The assistant
    reply arrives later via the WebSocket channel (out of scope for this test)."""
    p = await make_proposal_api(client, registered.headers)
    resp = await client.post(
        f"{API}/chat/{p['id']}/send",
        headers=registered.headers,
        json={"content": "Acme needs a rebrand"},
    )
    assert resp.status_code == 201
    msgs = resp.json()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Acme needs a rebrand"

    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "analyze_brief"

    # The proposal's job_status reflects the queued phase
    prop = await client.get(f"{API}/proposals/{p['id']}", headers=registered.headers)
    job_status = prop.json()["pipeline_state"]["job_status"]
    assert job_status == {"phase": "analyze_brief", "state": "queued", "error": None}


async def test_approve_brief_gate_advances_pipeline(client, registered, seeded_templates, make_proposal_api):
    """The brief gate stays synchronous — template matching is a local lookup,
    no LLM/IO involved — so this test exercises the full handler."""
    p = await make_proposal_api(client, registered.headers)
    resp = await client.post(
        f"{API}/chat/{p['id']}/approve/brief", headers=registered.headers, json={"data": {}}
    )
    assert resp.status_code == 200

    prop = await client.get(f"{API}/proposals/{p['id']}", headers=registered.headers)
    pipeline = prop.json()["pipeline_state"]
    assert pipeline["current_phase"] == "template_confirm"
    assert "brief" in pipeline["phases_completed"]


async def test_approve_template_gate_enqueues_research(client, registered, arq_pool, seeded_templates, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    # advance the proposal to template_confirm via the brief gate
    await client.post(f"{API}/chat/{p['id']}/approve/brief", headers=registered.headers, json={"data": {}})

    resp = await client.post(
        f"{API}/chat/{p['id']}/approve/template",
        headers=registered.headers,
        json={"data": {"template_key": "brand_identity"}},
    )
    assert resp.status_code == 200
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"

    prop = await client.get(f"{API}/proposals/{p['id']}", headers=registered.headers)
    pipeline = prop.json()["pipeline_state"]
    assert pipeline["current_phase"] == "research"
    assert pipeline["job_status"]["state"] == "queued"


async def test_approve_unknown_gate_400(client, registered, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    resp = await client.post(
        f"{API}/chat/{p['id']}/approve/bogus-gate", headers=registered.headers, json={"data": {}}
    )
    assert resp.status_code == 400


async def test_patch_cost_model_item_recalculates_totals(client, registered, db, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)

    # seed a cost model directly on the proposal
    repo = ProposalRepository(db)
    await repo.update(
        p["id"],
        cost_model={
            "line_items": [
                {"deliverable": "Logo", "quantity": 1, "unit_cost": 100000, "total": 100000},
                {"deliverable": "Site", "quantity": 1, "unit_cost": 200000, "total": 200000},
            ],
            "subtotal": 300000,
            "discount_percent": 0,
            "discount_amount": 0,
            "total": 300000,
            "gst_amount": 54000,
            "grand_total": 354000,
        },
    )
    await db.commit()

    resp = await client.patch(
        f"{API}/chat/{p['id']}/cost-model",
        headers=registered.headers,
        json={"index": 0, "field": "quantity", "value": 3},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["line_items"][0]["quantity"] == 3
    assert updated["line_items"][0]["total"] == 300000  # 100000 * 3
    assert updated["subtotal"] == 500000  # 300000 + 200000
    assert updated["gst_amount"] == 90000  # int(500000 * 0.18)
    assert updated["grand_total"] == 590000

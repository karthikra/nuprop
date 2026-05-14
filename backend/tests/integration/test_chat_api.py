"""Integration tests for the chat API — messages, send, approval gates,
and the cost-model line-item patch."""

from __future__ import annotations

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from tests.conftest import API


async def _make_proposal(http, headers):
    c = (await http.post(f"{API}/clients", headers=headers, json={"name": "Chat Client"})).json()
    p = (
        await http.post(
            f"{API}/proposals",
            headers=headers,
            json={"client_id": c["id"], "project_name": "Chat Project"},
        )
    ).json()
    return p


async def test_get_messages_empty(client, registered):
    p = await _make_proposal(client, registered.headers)
    resp = await client.get(f"{API}/chat/{p['id']}/messages", headers=registered.headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_messages_cross_agency_404(client, registered, second_agency):
    p = await _make_proposal(client, registered.headers)
    resp = await client.get(f"{API}/chat/{p['id']}/messages", headers=second_agency.headers)
    assert resp.status_code == 404


async def test_send_message_echo_path_when_ai_not_configured(client, registered):
    """With no API key the brief phase falls back to an echo response."""
    p = await _make_proposal(client, registered.headers)
    resp = await client.post(
        f"{API}/chat/{p['id']}/send",
        headers=registered.headers,
        json={"content": "We need a rebrand for Acme"},
    )
    assert resp.status_code == 201
    msgs = resp.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "We need a rebrand for Acme"
    assert msgs[1]["role"] == "assistant"


async def test_send_message_ai_path_completes_brief(client, registered, monkeypatch):
    """With AI 'configured' and BriefAnalyzer mocked, a completed brief is
    persisted on the proposal and surfaced as a brief_summary message."""
    from app.infrastructure.external.anthropic_client import AnthropicClient
    from app.services.ai.brief_analyzer import BriefAnalysisResult, BriefAnalyzer

    monkeypatch.setattr(AnthropicClient, "is_configured", property(lambda self: True))

    async def fake_analyze(self, chat_history, current_brief):
        return BriefAnalysisResult(
            response_text="Here's the brief — confirm?",
            brief_complete=True,
            brief_data={"client": {"name": "Acme"}, "project": {"type": "rebrand"}},
        )

    monkeypatch.setattr(BriefAnalyzer, "analyze", fake_analyze)

    p = await _make_proposal(client, registered.headers)
    resp = await client.post(
        f"{API}/chat/{p['id']}/send",
        headers=registered.headers,
        json={"content": "Acme needs a rebrand"},
    )
    assert resp.status_code == 201
    assistant = resp.json()[1]
    assert assistant["message_type"] == "brief_summary"
    assert assistant["extra_data"]["requires_approval"] is True

    # the completed brief is persisted on the proposal
    prop = await client.get(f"{API}/proposals/{p['id']}", headers=registered.headers)
    assert prop.json()["brief"]["client"]["name"] == "Acme"


async def test_approve_brief_gate_advances_pipeline(client, registered, seeded_templates):
    p = await _make_proposal(client, registered.headers)
    resp = await client.post(
        f"{API}/chat/{p['id']}/approve/brief", headers=registered.headers, json={"data": {}}
    )
    assert resp.status_code == 200

    prop = await client.get(f"{API}/proposals/{p['id']}", headers=registered.headers)
    pipeline = prop.json()["pipeline_state"]
    assert pipeline["current_phase"] == "template_confirm"
    assert "brief" in pipeline["phases_completed"]


async def test_approve_unknown_gate_400(client, registered):
    p = await _make_proposal(client, registered.headers)
    resp = await client.post(
        f"{API}/chat/{p['id']}/approve/bogus-gate", headers=registered.headers, json={"data": {}}
    )
    assert resp.status_code == 400


async def test_patch_cost_model_item_recalculates_totals(client, registered, db):
    p = await _make_proposal(client, registered.headers)

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

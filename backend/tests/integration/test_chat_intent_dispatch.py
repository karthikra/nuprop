"""Integration tests for Path B dispatch: a non-brief chat message is
classified and routed to the right action, producing an ack message. The
classifier is patched at the viewmodel's import site so dispatch is
deterministic without a real Bedrock call."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository

API = "/api/v1"


def _patch_intent(monkeypatch, intent: dict):
    import app.viewmodels.chat_viewmodel as vm
    monkeypatch.setattr(vm, "classify_intent", AsyncMock(return_value=intent))


async def _move_out_of_brief(client, headers, pid):
    # advance past brief so send_message takes the Path B branch
    await client.post(f"{API}/chat/{pid}/approve/brief", headers=headers, json={"data": {}})


@pytest.mark.asyncio
async def test_re_run_phase_enqueues_job_and_acks(
    client, registered, arq_pool, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {"kind": "re_run_phase", "phase": "research", "confidence": 0.95})
    p = await make_proposal_api(client, registered.headers)
    await _move_out_of_brief(client, registered.headers, p["id"])
    arq_pool.reset_mock()

    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "redo the research"},
    )
    assert resp.status_code == 201
    arq_pool.delete.assert_awaited()
    assert arq_pool.delete.await_args.args[0] == f"arq:result:{p['id']}:run_research"
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"
    text = " ".join((m.get("content") or "") for m in resp.json()).lower()
    assert "research" in text


@pytest.mark.asyncio
async def test_unknown_intent_returns_help_and_enqueues_nothing(
    client, registered, arq_pool, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {"kind": "unknown", "confidence": 0.0})
    p = await make_proposal_api(client, registered.headers)
    await _move_out_of_brief(client, registered.headers, p["id"])
    arq_pool.reset_mock()

    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "asdfgh"},
    )
    assert resp.status_code == 201
    arq_pool.enqueue_job.assert_not_awaited()
    text = " ".join((m.get("content") or "") for m in resp.json()).lower()
    assert "re-run" in text or "regenerate" in text or "refine" in text


@pytest.mark.asyncio
async def test_edit_cost_item_updates_model(
    client, registered, db, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {
        "kind": "edit_cost_item", "deliverable": "Logo",
        "field": "quantity", "value": 2, "confidence": 0.9,
    })
    p = await make_proposal_api(client, registered.headers)
    repo = ProposalRepository(db)
    await repo.update(
        p["id"],
        pipeline_state={"current_phase": "cost_model_review"},
        cost_model={"line_items": [
            {"deliverable": "Logo", "quantity": 1, "unit_cost": 100000, "total": 100000},
        ], "discount_percent": 0},
    )
    await db.commit()

    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "set Logo quantity to 2"},
    )
    assert resp.status_code == 201
    fresh = await repo.get_by_id(p["id"])
    assert fresh.cost_model["line_items"][0]["quantity"] == 2
    assert fresh.cost_model["line_items"][0]["total"] == 200000


@pytest.mark.asyncio
async def test_edit_cost_item_unknown_deliverable_acks_gracefully(
    client, registered, db, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {
        "kind": "edit_cost_item", "deliverable": "Nonexistent",
        "field": "quantity", "value": 2, "confidence": 0.9,
    })
    p = await make_proposal_api(client, registered.headers)
    repo = ProposalRepository(db)
    await repo.update(
        p["id"], pipeline_state={"current_phase": "cost_model_review"},
        cost_model={"line_items": [{"deliverable": "Logo", "quantity": 1, "unit_cost": 100000, "total": 100000}], "discount_percent": 0},
    )
    await db.commit()
    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "set Foo quantity to 2"},
    )
    assert resp.status_code == 201  # graceful ack, not a 500
    text = " ".join((m.get("content") or "") for m in resp.json()).lower()
    assert "couldn't find" in text or "could not find" in text


@pytest.mark.asyncio
async def test_regenerate_section_preserves_assets(
    client, registered, db, make_proposal_api, monkeypatch,
):
    """Chat-triggered regen must NOT wipe assets (guards the S10 A8 bug via
    the chat path)."""
    _patch_intent(monkeypatch, {
        "kind": "regenerate_section", "section_type": "problem_statement", "confidence": 0.95,
    })
    # Mock the section generation so no LLM runs; return a fresh payload WITHOUT assets.
    import app.viewmodels.chat_viewmodel as vm
    monkeypatch.setattr(
        vm, "regenerate_section_content",
        AsyncMock(return_value={"content": "new problem statement", "assets": []}),
    )
    p = await make_proposal_api(client, registered.headers)
    repo = ProposalRepository(db)
    await repo.update(
        p["id"],
        pipeline_state={"current_phase": "section_editor"},
        problem_statement={"content": "old", "assets": [{"id": "a1", "s3_key": "k1"}]},
    )
    await db.commit()
    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "regenerate the problem statement"},
    )
    assert resp.status_code == 201
    fresh = await repo.get_by_id(p["id"])
    assert fresh.problem_statement["content"] == "new problem statement"
    # assets preserved from the prior version
    assert fresh.problem_statement["assets"] == [{"id": "a1", "s3_key": "k1"}]


@pytest.mark.asyncio
async def test_refine_section_preserves_assets_and_acks(
    client, registered, db, make_proposal_api, monkeypatch,
):
    """refine_section shares the regenerate persistence path: it must preserve
    assets and ack with a 'Refining' verb."""
    _patch_intent(monkeypatch, {
        "kind": "refine_section", "section_type": "cover_page",
        "instructions": "make it punchier", "confidence": 0.9,
    })
    import app.viewmodels.chat_viewmodel as vm
    captured: dict = {}

    async def _fake_regen(proposal, section_type, instructions, db):  # noqa: ANN001
        captured["instructions"] = instructions
        return {"content": "punchier cover", "assets": []}

    monkeypatch.setattr(vm, "regenerate_section_content", _fake_regen)
    p = await make_proposal_api(client, registered.headers)
    repo = ProposalRepository(db)
    await repo.update(
        p["id"],
        pipeline_state={"current_phase": "section_editor"},
        cover_page={"content": "old cover", "assets": [{"id": "c1", "s3_key": "ck1"}]},
    )
    await db.commit()
    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "make the cover page punchier"},
    )
    assert resp.status_code == 201
    # refine passes the user's guidance through to the generator
    assert captured["instructions"] == "make it punchier"
    fresh = await repo.get_by_id(p["id"])
    assert fresh.cover_page["content"] == "punchier cover"
    assert fresh.cover_page["assets"] == [{"id": "c1", "s3_key": "ck1"}]
    text = " ".join((m.get("content") or "") for m in resp.json()).lower()
    assert "refin" in text


@pytest.mark.asyncio
async def test_crafted_section_type_is_rejected_and_does_not_write(
    client, registered, db, make_proposal_api, monkeypatch,
):
    """A non-canonical section_type from the classifier must NOT reach
    getattr/repo.update (which would read/write an arbitrary model column).
    It must ack gracefully and leave the row untouched."""
    _patch_intent(monkeypatch, {
        "kind": "regenerate_section", "section_type": "agency_id", "confidence": 0.95,
    })
    p = await make_proposal_api(client, registered.headers)
    repo = ProposalRepository(db)
    original = await repo.get_by_id(p["id"])
    original_agency = str(original.agency_id)
    await repo.update(p["id"], pipeline_state={"current_phase": "section_editor"})
    await db.commit()

    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "regenerate the agency thing"},
    )
    assert resp.status_code == 201
    fresh = await repo.get_by_id(p["id"])
    # agency_id (and the row) untouched — no arbitrary-column write happened
    assert str(fresh.agency_id) == original_agency
    text = " ".join((m.get("content") or "") for m in resp.json()).lower()
    assert "don't recognize" in text or "do not recognize" in text or "unrecognize" in text


@pytest.mark.asyncio
async def test_ask_question_answers_with_assistant_text(
    client, registered, make_proposal_api, monkeypatch,
):
    _patch_intent(monkeypatch, {
        "kind": "ask_question", "question": "what's my total?", "confidence": 0.8,
    })
    import app.viewmodels.chat_viewmodel as vm
    fake = AsyncMock(return_value=type("R", (), {"text": "Your total is Rs.1,18,000."})())
    monkeypatch.setattr(vm, "get_ai_service", lambda: AsyncMock(complete=fake), raising=False)
    p = await make_proposal_api(client, registered.headers)
    await _move_out_of_brief(client, registered.headers, p["id"])
    resp = await client.post(
        f"{API}/chat/{p['id']}/send", headers=registered.headers,
        json={"content": "what's my total?"},
    )
    assert resp.status_code == 201
    text = " ".join((m.get("content") or "") for m in resp.json()).lower()
    assert "total" in text

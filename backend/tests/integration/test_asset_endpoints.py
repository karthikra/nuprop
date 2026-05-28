"""Integration tests for section-asset endpoints.

POST   /api/v1/proposals/{id}/sections/{type}/assets/presign
POST   /api/v1/proposals/{id}/sections/{type}/assets/commit
POST   /api/v1/proposals/{id}/sections/{type}/assets/generate
DELETE /api/v1/proposals/{id}/sections/{type}/assets/{asset_id}
"""
from __future__ import annotations

import pytest_asyncio

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from tests.conftest import API


async def _fresh_get(proposal_id):
    """Load a proposal in a fresh session — bypasses the test fixture's stale identity map."""
    async with async_session_factory() as s:
        return await ProposalRepository(s).get_by_id(proposal_id)


async def _setup(http, headers):
    c = (await http.post(f"{API}/clients", headers=headers, json={"name": "Assets Client"})).json()
    p = (await http.post(
        f"{API}/proposals",
        headers=headers,
        json={"client_id": c["id"], "project_name": "Assets Project"},
    )).json()
    return p


@pytest_asyncio.fixture
async def _proposal(client, registered, db):
    p = await _setup(client, registered.headers)
    # Stamp a section so /commit and /delete have somewhere to read from.
    await ProposalRepository(db).update(
        p["id"],
        problem_statement={"content": "x", "assets": [], "included": True, "metadata": {}},
    )
    await db.commit()
    proposal = await ProposalRepository(db).get_by_id(p["id"])
    return proposal, registered.headers


# ── presign ──────────────────────────────────────────────────────────────────
async def test_presign_returns_upload_url_and_asset_id(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "hero.png", "content_type": "image/png", "size": 1024},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["upload_url"].startswith("https://s3.example/")
    assert body["s3_key"].endswith(".png")
    assert body["s3_key"].startswith(f"{proposal.agency_id}/{proposal.id}/")
    assert "asset_id" in body


async def test_presign_rejects_oversize_image(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "huge.png", "content_type": "image/png", "size": 11 * 1024 * 1024},
    )
    assert r.status_code == 400
    assert "exceeds max size" in r.json()["detail"]


async def test_presign_rejects_wrong_mime(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "doc.pdf", "content_type": "application/pdf", "size": 1024},
    )
    assert r.status_code == 400
    assert "not allowed for image" in r.json()["detail"]


async def test_presign_unknown_section_type_returns_400(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/not_a_section/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "x.png", "content_type": "image/png", "size": 100},
    )
    assert r.status_code == 400


# ── commit ───────────────────────────────────────────────────────────────────
async def test_commit_appends_asset_to_section(client, _proposal, db):
    proposal, headers = _proposal
    r1 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "h.png", "content_type": "image/png", "size": 1024},
    )
    presigned = r1.json()

    r2 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=headers,
        json={
            "asset_id": presigned["asset_id"],
            "s3_key": presigned["s3_key"],
            "kind": "image",
            "content_type": "image/png",
            "caption": "hero shot",
            "width": 1024,
            "height": 768,
        },
    )
    assert r2.status_code == 200, r2.text
    asset = r2.json()
    assert asset["id"] == presigned["asset_id"]
    assert asset["s3_key"] == presigned["s3_key"]
    assert asset["caption"] == "hero shot"
    assert asset["ai_generated"] is False
    assert asset["provider"] == "upload"
    assert asset["url"].startswith("https://s3.example/")

    # Verify it was persisted on the section's assets list.
    refreshed = await _fresh_get(proposal.id)
    assert refreshed.problem_statement["assets"][0]["id"] == presigned["asset_id"]


async def test_commit_persists_when_section_column_is_null(client, _proposal, db):
    """Committing to a section that's still NULL initialises a default payload."""
    proposal, headers = _proposal
    # Wipe the section back to NULL.
    await ProposalRepository(db).update(proposal.id, problem_statement=None)
    await db.commit()

    r1 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "h.png", "content_type": "image/png", "size": 1024},
    )
    p = r1.json()
    r2 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=headers,
        json={
            "asset_id": p["asset_id"],
            "s3_key": p["s3_key"],
            "kind": "image",
            "content_type": "image/png",
            "caption": None,
            "width": None,
            "height": None,
        },
    )
    assert r2.status_code == 200

    refreshed = await _fresh_get(proposal.id)
    section = refreshed.problem_statement
    assert section["content"] == ""
    assert section["included"] is True
    assert len(section["assets"]) == 1


# ── generate ─────────────────────────────────────────────────────────────────
async def test_generate_image_appends_ai_asset(client, _proposal, db, monkeypatch):
    proposal, headers = _proposal

    async def _fake_generate_image(*, prompt, agency_id, proposal_id):
        return {
            "id": "ai-asset-1",
            "kind": "image",
            "s3_key": f"{agency_id}/{proposal_id}/ai-asset-1.png",
            "url": "https://s3.example/will-be-overwritten?signed=fake",
            "caption": None,
            "ai_generated": True,
            "prompt": prompt,
            "provider": "fal-ai/nano-banana",
            "width": 1024,
            "height": 1024,
            "duration_s": None,
            "poster_s3_key": None,
        }

    import app.views.v1.proposals as proposals_view
    monkeypatch.setattr(proposals_view, "generate_image", _fake_generate_image, raising=False)

    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/generate",
        headers=headers,
        json={"kind": "image", "prompt": "an astronaut"},
    )
    assert r.status_code == 200, r.text
    asset = r.json()
    assert asset["ai_generated"] is True
    assert asset["prompt"] == "an astronaut"
    # The handler re-signs via the test stub of generate_presigned_get.
    assert asset["url"] == f"https://s3.example/{asset['s3_key']}?signed=test"

    refreshed = await _fresh_get(proposal.id)
    assert refreshed.problem_statement["assets"][0]["id"] == "ai-asset-1"


async def test_generate_rejects_non_image_kind_in_s10(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/generate",
        headers=headers,
        json={"kind": "video", "prompt": "x"},
    )
    assert r.status_code == 400
    assert "image" in r.json()["detail"]


# ── delete ───────────────────────────────────────────────────────────────────
async def test_delete_removes_asset_from_section(client, _proposal, db, monkeypatch):
    proposal, headers = _proposal
    # Seed an asset directly.
    await ProposalRepository(db).update(
        proposal.id,
        problem_statement={
            "content": "x",
            "assets": [{"id": "a1", "kind": "image", "s3_key": "k1"}],
            "included": True,
            "metadata": {},
        },
    )
    await db.commit()

    deleted: list[str] = []

    async def _fake_delete(key):
        deleted.append(key)

    monkeypatch.setattr("app.services.media._s3.delete_object", _fake_delete, raising=False)

    r = await client.delete(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/a1",
        headers=headers,
    )
    assert r.status_code == 204
    assert deleted == ["k1"]

    refreshed = await _fresh_get(proposal.id)
    assert refreshed.problem_statement["assets"] == []


async def test_delete_missing_asset_returns_404(client, _proposal):
    proposal, headers = _proposal
    r = await client.delete(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/missing",
        headers=headers,
    )
    assert r.status_code == 404


# ── IDOR isolation ───────────────────────────────────────────────────────────
async def test_asset_endpoints_404_for_other_agency(client, _proposal, second_agency):
    proposal, _ = _proposal
    rival = second_agency.headers

    presign = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=rival,
        json={"kind": "image", "filename": "x.png", "content_type": "image/png", "size": 100},
    )
    assert presign.status_code == 404

    commit = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=rival,
        json={
            "asset_id": "x", "s3_key": "k", "kind": "image",
            "content_type": "image/png", "caption": None, "width": None, "height": None,
        },
    )
    assert commit.status_code == 404

    gen = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/generate",
        headers=rival,
        json={"kind": "image", "prompt": "x"},
    )
    assert gen.status_code == 404

    delete = await client.delete(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/x",
        headers=rival,
    )
    assert delete.status_code == 404


# ── New IDOR + validation coverage ──────────────────────────────────────────


async def test_commit_rejects_s3_key_outside_proposal_prefix(client, _proposal):
    """A crafted s3_key from another proposal/agency must be rejected."""
    proposal, headers = _proposal
    # First presign legitimately to get a valid asset_id shape.
    r1 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "h.png", "content_type": "image/png", "size": 1024},
    )
    p = r1.json()
    # Now commit with a foreign-prefixed s3_key.
    r2 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=headers,
        json={
            "asset_id": p["asset_id"],
            "s3_key": "other-agency-uuid/other-proposal-uuid/asset.png",
            "kind": "image",
            "content_type": "image/png",
            "caption": None,
            "width": None,
            "height": None,
        },
    )
    assert r2.status_code == 400
    assert "does not belong" in r2.json()["detail"]


async def test_commit_rejects_kind_mismatch_with_content_type(client, _proposal):
    """Cannot commit kind=image with content_type=video/mp4 (mismatch).

    Note: in S10 the endpoint short-circuits on kind!="image" with an
    "image only" 400. To exercise the kind/content-type consistency check
    that lives further down, we hold kind=image and lie about content_type.
    """
    proposal, headers = _proposal
    r1 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "h.png", "content_type": "image/png", "size": 1024},
    )
    p = r1.json()
    r2 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=headers,
        json={
            "asset_id": p["asset_id"],
            "s3_key": p["s3_key"],
            "kind": "image",
            "content_type": "video/mp4",
            "caption": None,
            "width": None,
            "height": None,
        },
    )
    assert r2.status_code == 400
    assert "does not match" in r2.json()["detail"]


async def test_commit_rejects_s3_key_ext_mismatch(client, _proposal):
    """Cannot commit s3_key with .png ext but content_type=image/jpeg."""
    proposal, headers = _proposal
    r1 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "image", "filename": "h.png", "content_type": "image/png", "size": 1024},
    )
    p = r1.json()
    r2 = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=headers,
        json={
            "asset_id": p["asset_id"],
            "s3_key": p["s3_key"],   # ends with .png
            "kind": "image",
            "content_type": "image/jpeg",  # expects .jpg
            "caption": None,
            "width": None,
            "height": None,
        },
    )
    assert r2.status_code == 400
    assert "s3_key extension" in r2.json()["detail"]


async def test_delete_on_null_section_returns_404(client, _proposal, db):
    """Section column NULL → 404 on delete (not 500)."""
    proposal, headers = _proposal
    # Wipe the section back to NULL so the not-current branch fires.
    await ProposalRepository(db).update(proposal.id, problem_statement=None)
    await db.commit()

    r = await client.delete(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/any-id",
        headers=headers,
    )
    assert r.status_code == 404


async def test_generate_translates_fal_runtime_error_to_502(client, _proposal, monkeypatch):
    """generate_image's RuntimeError must surface as a 502 (not a 500)."""
    proposal, headers = _proposal

    async def _fake_generate_image(*, prompt, agency_id, proposal_id):
        raise RuntimeError("fal.ai endpoint fal-ai/nano-banana returned no images")

    import app.views.v1.proposals as proposals_view
    monkeypatch.setattr(proposals_view, "generate_image", _fake_generate_image, raising=False)

    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/generate",
        headers=headers,
        json={"kind": "image", "prompt": "x"},
    )
    assert r.status_code == 502
    assert "Image generation failed" in r.json()["detail"]


async def test_get_proposal_resigns_every_asset_url(client, _proposal, db):
    proposal, headers = _proposal
    # Seed two assets directly, both with stale URLs.
    await ProposalRepository(db).update(
        proposal.id,
        problem_statement={
            "content": "x",
            "assets": [
                {"id": "a1", "kind": "image", "s3_key": "k1", "url": "stale-1"},
                {"id": "a2", "kind": "image", "s3_key": "k2", "url": "stale-2"},
            ],
            "included": True,
            "metadata": {},
        },
    )
    await db.commit()

    r = await client.get(f"{API}/proposals/{proposal.id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assets = body["problem_statement"]["assets"]
    assert assets[0]["url"] == "https://s3.example/k1?signed=test"
    assert assets[1]["url"] == "https://s3.example/k2?signed=test"


# ── Regression: regenerate/refine must preserve assets ───────────────────────


async def test_regenerate_section_preserves_existing_assets(client, _proposal, db, monkeypatch):
    """Regenerating a section must NOT wipe its assets (Critical data-loss fix)."""
    proposal, headers = _proposal
    # Seed an asset directly on the section.
    await ProposalRepository(db).update(
        proposal.id,
        problem_statement={
            "content": "before",
            "assets": [{"id": "a1", "kind": "image", "s3_key": "k1"}],
            "included": True,
            "metadata": {},
        },
    )
    await db.commit()

    # Mock the fact generator so regenerate returns a clean payload with empty assets.
    async def _fake_fact(section_type, **_):
        return {"content": "after", "assets": [], "included": True, "metadata": {}}

    from app.services.ai import section_facts
    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)
    import app.services.sections.regeneration as regeneration
    monkeypatch.setattr(regeneration, "generate_fact_section", _fake_fact, raising=False)

    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/regenerate",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "after"
    # The asset must survive.
    assert len(body["assets"]) == 1
    assert body["assets"][0]["id"] == "a1"


async def test_refine_section_preserves_existing_assets(client, _proposal, db, monkeypatch):
    """Refining a section must NOT wipe its assets (Critical data-loss fix)."""
    proposal, headers = _proposal
    await ProposalRepository(db).update(
        proposal.id,
        problem_statement={
            "content": "before",
            "assets": [{"id": "a1", "kind": "image", "s3_key": "k1"}],
            "included": True,
            "metadata": {},
        },
    )
    await db.commit()

    async def _fake_fact(section_type, **_):
        return {"content": "refined", "assets": [], "included": True, "metadata": {}}

    from app.services.ai import section_facts
    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)
    import app.services.sections.regeneration as regeneration
    monkeypatch.setattr(regeneration, "generate_fact_section", _fake_fact, raising=False)

    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/refine",
        headers=headers,
        json={"instructions": "shorter please"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "refined"
    assert len(body["assets"]) == 1


async def test_generate_does_not_persist_transient_url(client, _proposal, db, monkeypatch):
    """The signed url returned by generate_image must NOT be stored verbatim
    in the JSON column — it'd expire in 1h. Persist with url=None; the GET
    re-sign path restores the URL on read."""
    proposal, headers = _proposal

    async def _fake_generate_image(*, prompt, agency_id, proposal_id):
        return {
            "id": "ai-1", "kind": "image",
            "s3_key": f"{agency_id}/{proposal_id}/ai-1.png",
            "url": "https://transient.example/will-expire",
            "caption": None, "ai_generated": True, "prompt": prompt,
            "provider": "fal-ai/nano-banana",
            "width": 1024, "height": 1024,
            "duration_s": None, "poster_s3_key": None,
        }

    import app.views.v1.proposals as proposals_view
    monkeypatch.setattr(proposals_view, "generate_image", _fake_generate_image, raising=False)

    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/generate",
        headers=headers,
        json={"kind": "image", "prompt": "x"},
    )
    assert r.status_code == 200

    # Open a fresh session so we see what was actually persisted (test fixture
    # session has identity-map cache).
    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refreshed = await ProposalRepository(fresh).get_by_id(proposal.id)
    persisted = refreshed.problem_statement["assets"][0]
    # Transient URL must NOT have leaked into the DB.
    assert persisted.get("url") is None


async def test_presign_rejects_non_image_kind_in_s10(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/presign",
        headers=headers,
        json={"kind": "video", "filename": "v.mp4", "content_type": "video/mp4", "size": 1024},
    )
    assert r.status_code == 400
    assert "image only" in r.json()["detail"]


async def test_commit_rejects_non_image_kind_in_s10(client, _proposal):
    proposal, headers = _proposal
    r = await client.post(
        f"{API}/proposals/{proposal.id}/sections/problem_statement/assets/commit",
        headers=headers,
        json={
            "asset_id": "a", "s3_key": "x/y/a.mp4", "kind": "video",
            "content_type": "video/mp4", "caption": None, "width": None, "height": None,
        },
    )
    assert r.status_code == 400
    assert "image only" in r.json()["detail"]

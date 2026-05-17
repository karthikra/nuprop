"""S2: POST /clients/{id}/context/preview must return the extracted structure
without persisting it. Distinct from POST /context which does both."""

from __future__ import annotations

from app.core.deps import get_context_service
from app.main import app
from tests.conftest import API


class _FakeCtx:
    def __init__(self):
        self.extract_calls: list[str] = []

    async def extract_context(self, raw_text: str) -> dict:
        self.extract_calls.append(raw_text)
        return {"relationship": {"status": "warm_intro", "primary_contact": {"name": "Priya"}}}

    # merge_context must NOT be called for preview
    async def merge_context(self, existing: dict, new: dict) -> dict:
        raise AssertionError("merge_context should not run during preview")


async def _make_client(http, headers, name: str = "Acme Co") -> str:
    resp = await http.post(f"{API}/clients", headers=headers, json={"name": name})
    return resp.json()["id"]


async def test_preview_returns_extracted_structure(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        client_id = await _make_client(client, registered.headers)
        resp = await client.post(
            f"{API}/clients/{client_id}/context/preview",
            headers=registered.headers,
            json={"raw_text": "Met Priya from Acme last week, warm intro from Suresh."},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "extracted" in body
        assert body["extracted"]["relationship"]["status"] == "warm_intro"
        assert fake.extract_calls == ["Met Priya from Acme last week, warm intro from Suresh."]
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_preview_does_not_persist(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        client_id = await _make_client(client, registered.headers)
        await client.post(
            f"{API}/clients/{client_id}/context/preview",
            headers=registered.headers,
            json={"raw_text": "anything"},
        )
        # GET the client and confirm context_profile is still empty
        get_resp = await client.get(f"{API}/clients/{client_id}", headers=registered.headers)
        assert get_resp.json()["context_profile"] == {}
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_preview_404_for_unknown_client(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        resp = await client.post(
            f"{API}/clients/00000000-0000-0000-0000-000000000000/context/preview",
            headers=registered.headers,
            json={"raw_text": "anything"},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_context_service, None)

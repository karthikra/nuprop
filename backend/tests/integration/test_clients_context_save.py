"""S2: POST /clients/{id}/context/save must merge a pre-extracted profile
into the client's existing context_profile, without re-calling the LLM."""

from __future__ import annotations

from app.core.deps import get_context_service
from app.main import app
from tests.conftest import API


class _FakeCtx:
    def __init__(self):
        self.merge_calls: list[tuple[dict, dict]] = []

    # extract_context must NOT be called for save
    async def extract_context(self, raw_text: str) -> dict:
        raise AssertionError("extract_context should not run during save")

    async def merge_context(self, existing: dict, new: dict) -> dict:
        self.merge_calls.append((existing, new))
        # Simple union for the test
        return {**existing, **new}


async def _make_client(http, headers, name: str = "Acme Co") -> str:
    resp = await http.post(f"{API}/clients", headers=headers, json={"name": name})
    return resp.json()["id"]


async def test_save_merges_profile_into_client(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        client_id = await _make_client(client, registered.headers)
        # Initial context — set via the existing PATCH so we test the merge path
        await client.patch(
            f"{API}/clients/{client_id}",
            headers=registered.headers,
            json={"context_profile": {"existing_key": "old"}},
        )
        # Save a new structure
        resp = await client.post(
            f"{API}/clients/{client_id}/context/save",
            headers=registered.headers,
            json={"profile": {"relationship": {"status": "warm_intro"}}},
        )
        assert resp.status_code == 200, resp.text

        # Confirm merge_context was called with (existing, new)
        assert len(fake.merge_calls) == 1
        existing, new = fake.merge_calls[0]
        assert existing == {"existing_key": "old"}
        assert new == {"relationship": {"status": "warm_intro"}}

        # GET the client and confirm context_profile is the merged result
        get_resp = await client.get(f"{API}/clients/{client_id}", headers=registered.headers)
        merged = get_resp.json()["context_profile"]
        assert merged == {"existing_key": "old", "relationship": {"status": "warm_intro"}}
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_save_returns_updated_client_response(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        client_id = await _make_client(client, registered.headers, name="Beta Inc")
        resp = await client.post(
            f"{API}/clients/{client_id}/context/save",
            headers=registered.headers,
            json={"profile": {"relationship": {"status": "existing_client"}}},
        )
        assert resp.status_code == 200
        body = resp.json()
        # The endpoint returns the full ClientResponse, like add_context does
        assert body["id"] == client_id
        assert body["name"] == "Beta Inc"
        assert body["context_profile"]["relationship"]["status"] == "existing_client"
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_save_404_for_unknown_client(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        resp = await client.post(
            f"{API}/clients/00000000-0000-0000-0000-000000000000/context/save",
            headers=registered.headers,
            json={"profile": {"x": "y"}},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_context_service, None)

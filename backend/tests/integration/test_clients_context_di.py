"""S1: `POST /clients/{id}/context` must use the injected ContextService so
tests can override it without monkeypatching."""

from __future__ import annotations

from app.core.deps import get_context_service
from app.main import app
from tests.conftest import API


class _FakeContextService:
    def __init__(self):
        self.calls = []

    async def extract_context(self, raw_text: str) -> dict:
        self.calls.append(("extract", raw_text))
        return {"relationship": {"status": "warm_intro"}}

    async def merge_context(self, existing: dict, new_extraction: dict) -> dict:
        self.calls.append(("merge", existing, new_extraction))
        return {**existing, **new_extraction}

    async def generate_context_brief(self, client_name: str, profile: dict) -> str:
        return f"brief for {client_name}"

    async def enrich_context_with_emails(self, profile, emails):
        return profile


async def test_add_context_uses_injected_service(client, registered):
    fake = _FakeContextService()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        c = await client.post(
            f"{API}/clients", headers=registered.headers,
            json={"name": "Acme Co"},
        )
        client_id = c.json()["id"]
        resp = await client.post(
            f"{API}/clients/{client_id}/context",
            headers=registered.headers,
            json={"raw_text": "some pasted email text"},
        )
        assert resp.status_code == 200
        assert fake.calls[0][0] == "extract"
        assert fake.calls[0][1] == "some pasted email text"
        assert fake.calls[1][0] == "merge"
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_context_brief_uses_injected_service(client, registered):
    fake = _FakeContextService()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        c = await client.post(
            f"{API}/clients", headers=registered.headers, json={"name": "Acme Co"},
        )
        client_id = c.json()["id"]
        # Seed context via the same injected fake
        await client.post(
            f"{API}/clients/{client_id}/context",
            headers=registered.headers,
            json={"raw_text": "seed"},
        )
        resp = await client.get(
            f"{API}/clients/{client_id}/context-brief",
            headers=registered.headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_context"] is True
        assert body["brief"] == "brief for Acme Co"
    finally:
        app.dependency_overrides.pop(get_context_service, None)

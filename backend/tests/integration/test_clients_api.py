"""Integration tests for the clients API — CRUD, search, and cross-agency
isolation (the IDOR fix)."""

from __future__ import annotations

import uuid

from tests.conftest import API


async def _create_client(http, headers, **overrides):
    payload = {"name": "Beta Corp", "industry": "retail", "tags": ["priority"]}
    payload.update(overrides)
    resp = await http.post(f"{API}/clients", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_client_generates_slug(client, registered):
    data = await _create_client(client, registered.headers, name="Beta Corp Ltd")
    assert data["slug"] == "beta-corp-ltd"
    assert data["industry"] == "retail"


async def test_list_clients(client, registered):
    await _create_client(client, registered.headers, name="Alpha")
    await _create_client(client, registered.headers, name="Bravo")
    resp = await client.get(f"{API}/clients", headers=registered.headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_search_clients_by_query(client, registered):
    await _create_client(client, registered.headers, name="Northwind Traders", industry="logistics")
    await _create_client(client, registered.headers, name="Southside Cafe", industry="hospitality")
    resp = await client.get(f"{API}/clients?q=northwind", headers=registered.headers)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Northwind Traders"]


async def test_filter_clients_by_industry(client, registered):
    await _create_client(client, registered.headers, name="A", industry="fintech")
    await _create_client(client, registered.headers, name="B", industry="retail")
    resp = await client.get(f"{API}/clients?industry=fintech", headers=registered.headers)
    assert [c["name"] for c in resp.json()] == ["A"]


async def test_get_client_by_id(client, registered):
    created = await _create_client(client, registered.headers)
    resp = await client.get(f"{API}/clients/{created['id']}", headers=registered.headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_get_nonexistent_client_404(client, registered):
    resp = await client.get(f"{API}/clients/{uuid.uuid4()}", headers=registered.headers)
    assert resp.status_code == 404


async def test_update_client_regenerates_slug(client, registered):
    created = await _create_client(client, registered.headers, name="Old Name")
    resp = await client.patch(
        f"{API}/clients/{created['id']}",
        headers=registered.headers,
        json={"name": "Brand New Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["slug"] == "brand-new-name"


async def test_delete_client(client, registered):
    created = await _create_client(client, registered.headers)
    resp = await client.delete(f"{API}/clients/{created['id']}", headers=registered.headers)
    assert resp.status_code == 204
    gone = await client.get(f"{API}/clients/{created['id']}", headers=registered.headers)
    assert gone.status_code == 404


# ── cross-agency isolation — IDOR fix 1a ─────────────────────────────────────
async def test_other_agency_cannot_read_client(client, registered, second_agency):
    created = await _create_client(client, registered.headers)
    resp = await client.get(f"{API}/clients/{created['id']}", headers=second_agency.headers)
    assert resp.status_code == 404


async def test_other_agency_cannot_update_client(client, registered, second_agency):
    created = await _create_client(client, registered.headers)
    resp = await client.patch(
        f"{API}/clients/{created['id']}",
        headers=second_agency.headers,
        json={"name": "Hijacked"},
    )
    assert resp.status_code == 404


async def test_other_agency_cannot_delete_client(client, registered, second_agency):
    created = await _create_client(client, registered.headers)
    resp = await client.delete(f"{API}/clients/{created['id']}", headers=second_agency.headers)
    assert resp.status_code == 404
    # the rightful owner still has the client
    still = await client.get(f"{API}/clients/{created['id']}", headers=registered.headers)
    assert still.status_code == 200


async def test_other_agency_clients_not_in_list(client, registered, second_agency):
    await _create_client(client, registered.headers, name="Acme Client")
    resp = await client.get(f"{API}/clients", headers=second_agency.headers)
    assert resp.json() == []

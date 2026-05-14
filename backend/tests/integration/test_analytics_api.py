"""Integration tests for the analytics API — overview, proposal detail, visitors."""

from __future__ import annotations

from tests.conftest import API


async def _make_proposal(http, headers, name="Analytics Project"):
    c = (await http.post(f"{API}/clients", headers=headers, json={"name": "Analytics Client"})).json()
    p = (
        await http.post(
            f"{API}/proposals",
            headers=headers,
            json={"client_id": c["id"], "project_name": name},
        )
    ).json()
    return p


async def test_overview_empty(client, registered):
    resp = await client.get(f"{API}/analytics/overview", headers=registered.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_proposals"] == 0
    assert data["avg_engagement_score"] == 0.0
    assert data["win_rate"] is None


async def test_overview_counts_proposals_by_status(client, registered):
    await _make_proposal(client, registered.headers, "P1")
    await _make_proposal(client, registered.headers, "P2")
    resp = await client.get(f"{API}/analytics/overview", headers=registered.headers)
    data = resp.json()
    assert data["total_proposals"] == 2
    assert data["proposals_by_status"]["draft"] == 2


async def test_proposal_analytics_detail(client, registered):
    p = await _make_proposal(client, registered.headers)
    resp = await client.get(f"{API}/analytics/proposals/{p['id']}", headers=registered.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["proposal_id"] == p["id"]
    assert data["unique_visitors"] == 0
    assert data["engagement_score"] == 0


async def test_proposal_analytics_cross_agency_404(client, registered, second_agency):
    p = await _make_proposal(client, registered.headers)
    resp = await client.get(
        f"{API}/analytics/proposals/{p['id']}", headers=second_agency.headers
    )
    assert resp.status_code == 404


async def test_proposal_visitors_empty(client, registered):
    p = await _make_proposal(client, registered.headers)
    resp = await client.get(
        f"{API}/analytics/proposals/{p['id']}/visitors", headers=registered.headers
    )
    assert resp.status_code == 200
    assert resp.json() == []

"""Health endpoint — also the smoke test for the whole test harness."""

from __future__ import annotations

from tests.conftest import API


async def test_health_check_returns_ok(client):
    resp = await client.get(f"{API}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "nuprop"}


async def test_unknown_route_404(client):
    resp = await client.get(f"{API}/this-route-does-not-exist")
    assert resp.status_code == 404

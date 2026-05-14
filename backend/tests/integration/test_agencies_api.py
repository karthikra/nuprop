"""Integration tests for the agencies API — profile, update, onboarding."""

from __future__ import annotations

from tests.conftest import API


async def test_get_my_agency(client, registered):
    resp = await client.get(f"{API}/agencies/me", headers=registered.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == registered.agency_id
    assert data["name"] == "Acme Agency"
    assert data["onboarding_complete"] is False


async def test_update_my_agency(client, registered):
    resp = await client.patch(
        f"{API}/agencies/me",
        headers=registered.headers,
        json={"name": "Acme Renamed", "gst_rate": 0.12},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Acme Renamed"
    assert data["gst_rate"] == 0.12


async def test_onboarding_steps_complete_the_flow(client, registered):
    h = registered.headers

    r1 = await client.post(
        f"{API}/agencies/me/onboarding",
        headers=h,
        json={"step": 1, "data": {"name": "Acme Co", "colours": {"primary": "#000"}}},
    )
    assert r1.status_code == 200
    assert r1.json()["name"] == "Acme Co"

    # step 2 creates a RateCard row
    r2 = await client.post(
        f"{API}/agencies/me/onboarding",
        headers=h,
        json={"step": 2, "data": {"version": "v1", "hourly_rates": {"design": 5000}}},
    )
    assert r2.status_code == 200
    rc = await client.get(f"{API}/rate-cards/active", headers=h)
    assert rc.status_code == 200
    assert rc.json()["version"] == "v1"

    r3 = await client.post(
        f"{API}/agencies/me/onboarding",
        headers=h,
        json={"step": 3, "data": {"voice_profile": "warm and direct"}},
    )
    assert r3.status_code == 200

    r4 = await client.post(
        f"{API}/agencies/me/onboarding", headers=h, json={"step": 4, "data": {}}
    )
    assert r4.status_code == 200
    assert r4.json()["onboarding_complete"] is True


async def test_onboarding_step1_omitting_logo_keeps_existing_logo(client, registered):
    """Regression test for the BaseRepository.update() None-drop fix.

    Set a logo, then run an onboarding step-1 update that omits ``logo_url`` —
    the existing logo must be preserved, not silently cleared.
    """
    h = registered.headers
    await client.patch(
        f"{API}/agencies/me", headers=h, json={"logo_url": "https://cdn.test/logo.png"}
    )
    resp = await client.post(
        f"{API}/agencies/me/onboarding",
        headers=h,
        json={"step": 1, "data": {"name": "Renamed Only"}},
    )
    assert resp.status_code == 200
    assert resp.json()["logo_url"] == "https://cdn.test/logo.png"

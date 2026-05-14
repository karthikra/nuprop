"""Integration tests for the rate-cards API — active card, versioning, and
cross-agency isolation (the IDOR fix)."""

from __future__ import annotations

from tests.conftest import API


async def _setup_rate_card(http, headers, version="v1"):
    resp = await http.post(
        f"{API}/agencies/me/onboarding",
        headers=headers,
        json={
            "step": 2,
            "data": {
                "version": version,
                "hourly_rates": {"design": 5000, "strategy": 8000},
                "offerings": {"branding": {"packages": {}}},
            },
        },
    )
    assert resp.status_code == 200, resp.text


async def test_get_active_rate_card(client, registered):
    await _setup_rate_card(client, registered.headers)
    resp = await client.get(f"{API}/rate-cards/active", headers=registered.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "v1"
    assert data["is_active"] is True
    assert data["hourly_rates"]["design"] == 5000


async def test_get_active_rate_card_404_when_none(client, registered):
    resp = await client.get(f"{API}/rate-cards/active", headers=registered.headers)
    assert resp.status_code == 404


async def test_list_rate_card_versions(client, registered):
    await _setup_rate_card(client, registered.headers, "v1")
    resp = await client.get(f"{API}/rate-cards", headers=registered.headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_create_version_deactivates_previous_and_clones(client, registered):
    await _setup_rate_card(client, registered.headers, "v1")
    resp = await client.post(
        f"{API}/rate-cards", headers=registered.headers, json={"version": "v2"}
    )
    assert resp.status_code == 201
    new = resp.json()
    assert new["version"] == "v2"
    assert new["is_active"] is True
    assert new["hourly_rates"]["design"] == 5000  # cloned from v1

    active = await client.get(f"{API}/rate-cards/active", headers=registered.headers)
    assert active.json()["version"] == "v2"  # only v2 is active now

    versions = await client.get(f"{API}/rate-cards", headers=registered.headers)
    assert len(versions.json()) == 2


async def test_update_rate_card(client, registered):
    await _setup_rate_card(client, registered.headers)
    active = (await client.get(f"{API}/rate-cards/active", headers=registered.headers)).json()
    resp = await client.patch(
        f"{API}/rate-cards/{active['id']}",
        headers=registered.headers,
        json={"pass_through_markup": 0.15},
    )
    assert resp.status_code == 200
    assert resp.json()["pass_through_markup"] == 0.15


# ── cross-agency isolation — IDOR fix 1b ─────────────────────────────────────
async def test_other_agency_cannot_update_rate_card(client, registered, second_agency):
    await _setup_rate_card(client, registered.headers)
    active = (await client.get(f"{API}/rate-cards/active", headers=registered.headers)).json()
    resp = await client.patch(
        f"{API}/rate-cards/{active['id']}",
        headers=second_agency.headers,
        json={"pass_through_markup": 0.99},
    )
    assert resp.status_code == 404
    # the rightful owner's rate card is untouched
    still = (await client.get(f"{API}/rate-cards/active", headers=registered.headers)).json()
    assert still["pass_through_markup"] != 0.99

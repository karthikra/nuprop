"""Integration tests for the templates API — system vs custom templates,
clone, and edit/delete protection."""

from __future__ import annotations

from tests.conftest import API


async def test_list_templates_includes_system_templates(client, registered, seeded_templates):
    resp = await client.get(f"{API}/templates", headers=registered.headers)
    assert resp.status_code == 200
    body = resp.json()
    keys = {t["template_key"] for t in body}
    assert {"brand_identity", "campaign"} <= keys
    assert all(t["is_system"] for t in body)


async def test_get_system_template(client, registered, seeded_templates):
    tmpl = seeded_templates[0]  # brand_identity
    resp = await client.get(f"{API}/templates/{tmpl.id}", headers=registered.headers)
    assert resp.status_code == 200
    assert resp.json()["template_key"] == "brand_identity"


async def test_create_custom_template(client, registered):
    resp = await client.post(
        f"{API}/templates",
        headers=registered.headers,
        json={"template_key": "my_custom", "name": "My Custom", "category": "brand", "config": {"x": 1}},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_system"] is False
    assert data["template_key"] == "my_custom"


async def test_cannot_update_system_template(client, registered, seeded_templates):
    tmpl = seeded_templates[1]  # campaign (system)
    resp = await client.patch(
        f"{API}/templates/{tmpl.id}", headers=registered.headers, json={"name": "Hacked"}
    )
    assert resp.status_code == 403


async def test_update_custom_template(client, registered):
    created = (
        await client.post(
            f"{API}/templates",
            headers=registered.headers,
            json={"template_key": "edit_me", "name": "Edit Me", "category": "brand"},
        )
    ).json()
    resp = await client.patch(
        f"{API}/templates/{created['id']}", headers=registered.headers, json={"name": "Edited"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Edited"


async def test_delete_custom_template(client, registered):
    created = (
        await client.post(
            f"{API}/templates",
            headers=registered.headers,
            json={"template_key": "del_me", "name": "Delete Me", "category": "brand"},
        )
    ).json()
    resp = await client.delete(f"{API}/templates/{created['id']}", headers=registered.headers)
    assert resp.status_code == 204


async def test_cannot_delete_system_template(client, registered, seeded_templates):
    tmpl = seeded_templates[0]  # brand_identity (system)
    resp = await client.delete(f"{API}/templates/{tmpl.id}", headers=registered.headers)
    assert resp.status_code == 403


async def test_clone_template_creates_agency_owned_copy(client, registered, seeded_templates):
    tmpl = seeded_templates[1]  # campaign
    resp = await client.post(
        f"{API}/templates/{tmpl.id}/clone",
        headers=registered.headers,
        json={"new_key": "campaign_copy", "new_name": "Campaign (Copy)"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_system"] is False
    assert data["template_key"] == "campaign_copy"
    assert data["category"] == "campaign"  # carried over from the source


async def test_other_agency_cannot_get_custom_template(client, registered, second_agency):
    created = (
        await client.post(
            f"{API}/templates",
            headers=registered.headers,
            json={"template_key": "private", "name": "Private", "category": "brand"},
        )
    ).json()
    resp = await client.get(f"{API}/templates/{created['id']}", headers=second_agency.headers)
    assert resp.status_code == 404

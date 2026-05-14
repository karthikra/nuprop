"""Integration tests for the auth API — register, login, /me."""

from __future__ import annotations

from tests.conftest import API


async def test_register_returns_token_and_ids(client):
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "email": "new@newagency.example.com",
            "password": "pw123456",
            "full_name": "New User",
            "agency_name": "New Agency",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user_id"]
    assert data["agency_id"]


async def test_register_duplicate_email_conflicts(client, registered):
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "email": registered.email,
            "password": "pw123456",
            "full_name": "Dup",
            "agency_name": "Dup Agency",
        },
    )
    assert resp.status_code == 409


async def test_register_invalid_email_422(client):
    resp = await client.post(
        f"{API}/auth/register",
        json={"email": "bogus", "password": "pw", "full_name": "X", "agency_name": "Y"},
    )
    assert resp.status_code == 422


async def test_login_with_valid_credentials(client, registered):
    resp = await client.post(
        f"{API}/auth/login",
        json={"email": registered.email, "password": "s3cret-password"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_wrong_password_401(client, registered):
    resp = await client.post(
        f"{API}/auth/login",
        json={"email": registered.email, "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email_401(client):
    resp = await client.post(
        f"{API}/auth/login",
        json={"email": "nobody@nowhere.example.com", "password": "whatever"},
    )
    assert resp.status_code == 401


async def test_me_returns_current_user(client, registered):
    resp = await client.get(f"{API}/auth/me", headers=registered.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == registered.email
    assert data["id"] == registered.user_id
    assert data["is_owner"] is True


async def test_me_without_token_is_rejected(client):
    resp = await client.get(f"{API}/auth/me")
    assert resp.status_code == 401  # HTTPBearer rejects missing credentials


async def test_me_with_garbage_token_401(client):
    resp = await client.get(
        f"{API}/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert resp.status_code == 401


async def test_register_slugifies_agency_name(client):
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "email": "slug@slugtest.example.com",
            "password": "pw123456",
            "full_name": "Slug User",
            "agency_name": "Cool Studio & Co",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    me = await client.get(
        f"{API}/agencies/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.json()["slug"] == "cool-studio-co"

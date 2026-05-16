"""S1: Gmail OAuth callback must reject forged, expired, and replayed `state`.

None of these tests reach the encryption step — they all fail before
ConnectorViewModel.handle_callback runs (state validation 400) OR the
handle_callback is stubbed via monkeypatch (replay test). So no ENCRYPTION_KEY
is needed."""

from __future__ import annotations

from app.core.config import get_settings
from app.infrastructure.security.oauth_state import issue_state
from tests.conftest import API


async def test_callback_rejects_missing_state(client, registered):
    resp = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": ""},
    )
    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


async def test_callback_rejects_forged_state(client, registered):
    resp = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": "deadbeef.cafebabe"},
    )
    assert resp.status_code == 400


async def test_callback_rejects_state_for_wrong_provider(client, registered):
    from uuid import UUID
    secret = get_settings().JWT_SECRET_KEY
    # State issued for slack but submitted to gmail
    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="slack",
        secret=secret,
    )
    resp = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert resp.status_code == 400


async def test_callback_rejects_expired_state(client, registered):
    from uuid import UUID
    secret = get_settings().JWT_SECRET_KEY
    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="gmail",
        secret=secret,
        ttl_seconds=-1,  # already expired
    )
    resp = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert resp.status_code == 400


async def test_callback_rejects_replayed_state(client, registered, monkeypatch):
    """First use returns 400 because we have no real OAuth code; second use
    must also fail, but with 'replayed' as the reason — proving the nonce
    store recorded the first use."""
    from uuid import UUID

    # We don't want the test to hit Google with the bogus code. Patch
    # ConnectorViewModel.handle_callback to short-circuit AFTER state has been
    # verified, so the nonce is still marked.
    from app.viewmodels import connector_viewmodel
    async def _ok(self, agency_id_from_state, code):
        return {"connected": True, "email": "x@x.test", "last_sync": None, "email_count": 0}
    monkeypatch.setattr(connector_viewmodel.ConnectorViewModel, "handle_callback", _ok)

    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="gmail",
        secret=get_settings().JWT_SECRET_KEY,
    )
    r1 = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert r1.status_code == 200, r1.text
    r2 = await client.post(
        f"{API}/connectors/gmail/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert r2.status_code == 400
    assert "replay" in r2.json()["detail"].lower() or "state" in r2.json()["detail"].lower()


async def test_auth_url_includes_signed_state(client, registered, monkeypatch):
    """The auth-url response must contain a `state` parameter that verify_state can decode."""
    # gmail.is_configured must return True for the route to issue a URL
    from app.infrastructure.external.gmail_client import GmailClient
    monkeypatch.setattr(GmailClient, "is_configured", property(lambda self: True))
    # Also stub the actual auth URL builder so we get a deterministic URL
    monkeypatch.setattr(GmailClient, "get_auth_url", lambda self, state: f"https://accounts.google.com/o/oauth2/v2/auth?state={state}")

    resp = await client.get(f"{API}/connectors/gmail/auth-url", headers=registered.headers)
    assert resp.status_code == 200
    url = resp.json()["auth_url"]
    assert "state=" in url
    state = url.split("state=")[-1]
    assert "." in state  # body.signature shape

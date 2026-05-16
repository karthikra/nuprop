"""S1: Slack OAuth callback must reject forged, expired, replayed `state`."""

from __future__ import annotations

from app.core.config import get_settings
from app.infrastructure.security.oauth_state import issue_state
from tests.conftest import API


async def test_slack_callback_rejects_forged_state(client, registered):
    resp = await client.post(
        f"{API}/connectors/slack/callback",
        headers=registered.headers,
        json={"code": "x", "state": "garbage.bytes"},
    )
    assert resp.status_code == 400


async def test_slack_callback_rejects_state_for_wrong_provider(client, registered):
    from uuid import UUID
    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="gmail",
        secret=get_settings().JWT_SECRET_KEY,
    )
    resp = await client.post(
        f"{API}/connectors/slack/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert resp.status_code == 400


async def test_slack_callback_rejects_replayed_state(client, registered, monkeypatch):
    from uuid import UUID
    from app.viewmodels import connector_viewmodel
    async def _ok(self, agency_id_from_state, code):
        return {"connected": True, "workspace": "Test"}
    monkeypatch.setattr(connector_viewmodel.ConnectorViewModel, "handle_slack_callback", _ok)

    state = issue_state(
        agency_id=UUID(registered.agency_id),
        provider="slack",
        secret=get_settings().JWT_SECRET_KEY,
    )
    r1 = await client.post(
        f"{API}/connectors/slack/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert r1.status_code == 200, r1.text
    r2 = await client.post(
        f"{API}/connectors/slack/callback",
        headers=registered.headers,
        json={"code": "x", "state": state},
    )
    assert r2.status_code == 400

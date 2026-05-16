"""Integration tests for the notifications API — listing, unread count, mark-read."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.infrastructure.db.models.notification import Notification
from tests.conftest import API


async def _seed_notification(db, agency_id, proposal_id):
    notif = Notification(
        proposal_id=proposal_id,
        agency_id=agency_id,
        alert_type="first_view",
        message="Opened for the first time",
        urgency="normal",
        channels_sent=[],
        sent_at=datetime.now(timezone.utc),
    )
    db.add(notif)
    await db.commit()
    return notif


async def test_list_notifications_empty(client, registered):
    resp = await client.get(f"{API}/notifications", headers=registered.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["unread_count"] == 0


async def test_unread_count_zero(client, registered):
    resp = await client.get(f"{API}/notifications/unread-count", headers=registered.headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_list_shows_seeded_notification(client, registered, db, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    await _seed_notification(db, registered.agency_id, p["id"])
    resp = await client.get(f"{API}/notifications", headers=registered.headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["unread_count"] == 1
    assert data["items"][0]["alert_type"] == "first_view"


async def test_mark_notification_read(client, registered, db, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    notif = await _seed_notification(db, registered.agency_id, p["id"])
    resp = await client.patch(
        f"{API}/notifications/{notif.id}/read", headers=registered.headers
    )
    assert resp.status_code == 200
    assert resp.json()["read_at"] is not None

    count = await client.get(f"{API}/notifications/unread-count", headers=registered.headers)
    assert count.json()["count"] == 0


async def test_mark_read_cross_agency_404(client, registered, second_agency, db, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)
    notif = await _seed_notification(db, registered.agency_id, p["id"])
    resp = await client.patch(
        f"{API}/notifications/{notif.id}/read", headers=second_agency.headers
    )
    assert resp.status_code == 404


async def test_mark_read_missing_notification_404(client, registered):
    resp = await client.patch(
        f"{API}/notifications/{uuid.uuid4()}/read", headers=registered.headers
    )
    assert resp.status_code == 404

"""Integration tests for the public /track analytics-beacon endpoint."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.infrastructure.db.models.analytics_event import AnalyticsEvent
from app.infrastructure.db.models.visitor import Visitor
from tests.conftest import API


async def test_track_empty_body_returns_204(client):
    resp = await client.post(f"{API}/track", content=b"")
    assert resp.status_code == 204


async def test_track_non_list_payload_returns_204(client):
    resp = await client.post(f"{API}/track", json={"not": "a list"})
    assert resp.status_code == 204


async def test_track_unknown_proposal_returns_204(client):
    events = [{"t": "page_view", "p": str(uuid.uuid4()), "sid": "s1"}]
    resp = await client.post(f"{API}/track", json=events)
    assert resp.status_code == 204


async def test_track_page_view_creates_visitor_and_event(client, registered, db, make_proposal_api):
    p = await make_proposal_api(client, registered.headers)

    events = [{"t": "page_view", "p": p["id"], "sid": "session-1"}]
    resp = await client.post(f"{API}/track", json=events)
    assert resp.status_code == 204

    # the /track endpoint commits on its own session — a fresh session sees it
    visitor_count = (
        await db.execute(
            select(func.count()).select_from(Visitor).where(Visitor.proposal_id == p["id"])
        )
    ).scalar()
    assert visitor_count == 1

    event_count = (
        await db.execute(
            select(func.count())
            .select_from(AnalyticsEvent)
            .where(AnalyticsEvent.proposal_id == p["id"])
        )
    ).scalar()
    assert event_count == 1

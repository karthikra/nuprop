from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.database import async_session_factory

router = APIRouter(tags=["analytics"])


@router.post("/track")
async def ingest_analytics(request: Request):
    """Receive analytics beacon events from proposal sites. No auth — public endpoint."""
    try:
        body = await request.body()
        if not body:
            return Response(status_code=204)

        events = json.loads(body)
        if not isinstance(events, list) or not events:
            return Response(status_code=204)

        # Extract proposal_id from first event
        proposal_id = events[0].get("p")
        if not proposal_id:
            return Response(status_code=204)

        # Store events (simple approach — write to DB)
        async with async_session_factory() as db:
            from app.infrastructure.db.models.analytics_event import AnalyticsEvent
            from app.infrastructure.db.models.base import IS_SQLITE
            from uuid import uuid4

            for event in events:
                ae = AnalyticsEvent(
                    proposal_id=proposal_id,
                    event_type=event.get("t", "unknown"),
                    data=event,
                    timestamp=datetime.now(timezone.utc),
                    section_id=event.get("section"),
                    card_id=event.get("card"),
                    session_id=event.get("sid"),
                    ip_city=None,
                )
                db.add(ae)

            await db.commit()

    except Exception:
        pass  # Silently ignore malformed beacons

    return Response(status_code=204)

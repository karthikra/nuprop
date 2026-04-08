from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.models.analytics_event import AnalyticsEvent
from app.infrastructure.db.models.base import IS_SQLITE, _uuid_default
from app.infrastructure.db.models.proposal import Proposal
from app.infrastructure.db.repositories.analytics_repo import AnalyticsRepository, compute_fingerprint
from app.services.engagement_scorer import compute_visitor_score

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

        proposal_id = events[0].get("p")
        if not proposal_id:
            return Response(status_code=204)

        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        fingerprint = compute_fingerprint(client_ip, user_agent)

        ua_lower = user_agent.lower()
        device_type = "mobile" if any(k in ua_lower for k in ("mobile", "iphone", "android")) else "desktop"

        async with async_session_factory() as db:
            repo = AnalyticsRepository(db)

            # Verify proposal exists
            pid = str(proposal_id) if IS_SQLITE else proposal_id
            result = await db.execute(select(Proposal).where(Proposal.id == pid))
            proposal = result.scalar_one_or_none()
            if not proposal:
                return Response(status_code=204)

            # Upsert visitor on page_view
            has_page_view = any(e.get("t") == "page_view" for e in events)
            visitor = None
            if has_page_view:
                visitor = await repo.upsert_visitor(proposal_id, fingerprint, None, device_type)
            else:
                visitor = await repo.get_visitor(proposal_id, fingerprint)

            visitor_id = (str(visitor.id) if IS_SQLITE else visitor.id) if visitor else None

            # Store events
            now = datetime.now(timezone.utc)
            total_duration = 0
            max_scroll = 0

            for event in events:
                ae = AnalyticsEvent(
                    id=_uuid_default(),
                    proposal_id=pid,
                    visitor_id=visitor_id,
                    event_type=event.get("t", "unknown"),
                    section_id=event.get("section"),
                    card_id=event.get("card"),
                    data=event,
                    timestamp=now,
                    session_id=event.get("sid"),
                    ip_city=None,
                )
                db.add(ae)

                if event.get("t") == "section_exit":
                    dur = event.get("duration", 0)
                    if isinstance(dur, (int, float)):
                        total_duration += int(dur)
                if event.get("t") == "scroll_depth":
                    depth = event.get("depth", 0)
                    if isinstance(depth, int) and depth > max_scroll:
                        max_scroll = depth

            # Update visitor stats
            if visitor and (total_duration > 0 or max_scroll > 0):
                await repo.update_visitor_stats(visitor, total_duration, max_scroll)

            # Compute engagement score
            if visitor:
                all_events = await repo.get_events(proposal_id, visitor.id)
                event_dicts = [
                    {
                        "t": e.event_type,
                        "section": e.section_id,
                        "card": e.card_id,
                        "duration": (e.data or {}).get("duration", 0),
                        "cta": (e.data or {}).get("cta", ""),
                    }
                    for e in all_events
                ]
                score = compute_visitor_score(
                    event_dicts, visitor.session_count, visitor.total_time_seconds,
                    visitor.first_seen, proposal.sent_at,
                )
                old_score = visitor.engagement_score
                await repo.update_visitor_score(visitor, score.total, score.classification)

                # Update proposal-level score
                all_visitors = await repo.get_visitors(proposal_id)
                from app.services.engagement_scorer import compute_proposal_score, EngagementBreakdown
                v_scores = []
                for v in all_visitors:
                    if v.id == visitor.id:
                        v_scores.append(score)
                    else:
                        dummy = EngagementBreakdown()
                        dummy.cta_clicked = v.engagement_score  # hack: just use total as one field
                        # Actually just create a mock with correct total
                        v_scores.append(type("S", (), {"total": v.engagement_score})())
                prop_score = compute_proposal_score(v_scores)
                proposal.engagement_score = prop_score

                # Evaluate notification rules
                try:
                    from app.services.notification_engine import evaluate_rules
                    notifications = evaluate_rules(
                        events=events, visitor=visitor, proposal=proposal,
                        previous_score=old_score, new_score=score.total,
                        visitor_count=len(all_visitors),
                    )
                    if notifications:
                        from app.infrastructure.db.models.notification import Notification
                        for n in notifications:
                            db.add(Notification(
                                id=_uuid_default(),
                                proposal_id=pid,
                                agency_id=str(proposal.agency_id) if IS_SQLITE else proposal.agency_id,
                                alert_type=n.alert_type,
                                message=n.message,
                                urgency=n.urgency,
                                channels_sent=[],
                                sent_at=now,
                            ))
                except Exception:
                    pass  # Don't let notification failures break tracking

            await db.commit()

    except Exception:
        pass

    return Response(status_code=204)

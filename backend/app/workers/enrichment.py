"""ARQ task: enrich client context profiles from synced emails.

Enqueued by ConnectorViewModel.sync_emails after it commits new email rows.
Terminal like the pipeline phases — a failure is logged, never retried, and
never propagates back to the sync that enqueued it. Per-client errors are
isolated so one bad client does not abort the rest.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.models.email_index import EmailIndex
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.services.context_service import ContextService

logger = logging.getLogger(__name__)


async def _enrich_clients(session, agency_id: str, client_ids: list[str]) -> None:
    """Core enrichment loop — separated from the ARQ wrapper so it's unit-testable."""
    client_repo = ClientRepository(session)
    context_service = ContextService()

    for client_id in client_ids:
        try:
            client = await client_repo.get_by_id(client_id)
            if client is None:
                continue

            result = await session.execute(
                select(EmailIndex).where(
                    EmailIndex.agency_id == str(agency_id),
                    EmailIndex.client_name == client.name,
                ).order_by(EmailIndex.date.desc())
            )
            rows = result.scalars().all()
            if not rows:
                continue

            email_summaries = [
                {
                    "date": row.date,
                    "message_type": row.message_type,
                    "sentiment": row.sentiment,
                    "subject": row.subject,
                    "summary": row.summary,
                }
                for row in rows
            ]

            merged = await context_service.enrich_context_with_emails(
                client.context_profile or {}, email_summaries
            )
            await client_repo.update(client.id, context_profile=merged)
            await session.commit()
            logger.info(
                "context enriched from emails",
                extra={"event": "connector.enrich.client_done",
                       "client_id": str(client.id), "email_count": len(rows)},
            )
        except Exception:  # noqa: BLE001 — isolate per-client failures
            logger.exception(
                "context enrichment failed for one client",
                extra={"event": "connector.enrich.client_failed", "client_id": str(client_id)},
            )
            await session.rollback()
            continue


async def enrich_context_from_emails(ctx, agency_id: str, client_ids: list[str]) -> None:
    """ARQ task entrypoint. Opens its own session; terminal on failure."""
    try:
        async with async_session_factory() as session:
            await _enrich_clients(session, agency_id, client_ids)
    except Exception:  # noqa: BLE001 — terminal, never re-raise
        logger.exception(
            "enrich_context_from_emails task failed",
            extra={"event": "connector.enrich.failed", "agency_id": str(agency_id)},
        )

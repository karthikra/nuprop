from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.domain.schemas.connector_schemas import (
    GmailAuthUrlResponse,
    GmailCallbackRequest,
    GmailStatusResponse,
    GmailSyncResponse,
)
from app.infrastructure.db.database import get_db
from app.viewmodels.connector_viewmodel import ConnectorViewModel

router = APIRouter(prefix="/connectors", tags=["connectors"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> ConnectorViewModel:
    return ConnectorViewModel(request, db)


@router.get("/gmail/auth-url", response_model=GmailAuthUrlResponse)
async def gmail_auth_url(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    url = await vm.get_auth_url(agency_id)
    if not url:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return GmailAuthUrlResponse(auth_url=url)


@router.post("/gmail/callback", response_model=GmailStatusResponse)
async def gmail_callback(
    body: GmailCallbackRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.handle_callback(agency_id, body.code)
    if not result:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return GmailStatusResponse(**result)


@router.get("/gmail/status", response_model=GmailStatusResponse)
async def gmail_status(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    return GmailStatusResponse(**(await vm.get_status(agency_id)))


@router.post("/gmail/sync", response_model=GmailSyncResponse)
async def gmail_sync(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.sync_emails(agency_id)
    if not result and vm.error:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return GmailSyncResponse(**result)


@router.delete("/gmail", status_code=status.HTTP_204_NO_CONTENT)
async def gmail_disconnect(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    await vm.disconnect(agency_id)


# ── Google Drive ─────────────────────────────────────────

@router.post("/drive/sync")
async def drive_sync(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    """Sync Google Drive documents for all clients. Requires Gmail to be connected (same Google account)."""
    result = await vm.sync_drive(agency_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Google Calendar ──────────────────────────────────────

@router.post("/calendar/sync")
async def calendar_sync(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    """Analyze calendar meeting patterns for all clients. Requires Gmail to be connected."""
    result = await vm.sync_calendar(agency_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Slack ────────────────────────────────────────────────

@router.get("/slack/auth-url")
async def slack_auth_url(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    url = await vm.get_slack_auth_url(agency_id)
    if not url:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return {"auth_url": url}


@router.post("/slack/callback")
async def slack_callback(
    body: GmailCallbackRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.handle_slack_callback(agency_id, body.code)
    if not result:
        raise HTTPException(status_code=400, detail="Slack connection failed")
    return result


@router.get("/slack/status")
async def slack_status(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    return await vm.get_slack_status(agency_id)


@router.post("/slack/sync")
async def slack_sync(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    result = await vm.sync_slack(agency_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/slack", status_code=status.HTTP_204_NO_CONTENT)
async def slack_disconnect(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ConnectorViewModel = Depends(get_vm),
):
    await vm.disconnect_slack(agency_id)

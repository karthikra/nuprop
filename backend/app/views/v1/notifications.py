from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.domain.schemas.notification_schemas import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.infrastructure.db.database import get_db
from app.viewmodels.notification_viewmodel import NotificationViewModel

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> NotificationViewModel:
    return NotificationViewModel(request, db)


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    skip: int = 0,
    limit: int = 20,
    unread_only: bool = False,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: NotificationViewModel = Depends(get_vm),
):
    return await vm.list_notifications(agency_id, skip, limit, unread_only)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: NotificationViewModel = Depends(get_vm),
):
    count = await vm.get_unread_count(agency_id)
    return UnreadCountResponse(count=count)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: NotificationViewModel = Depends(get_vm),
):
    result = await vm.mark_as_read(notification_id, agency_id)
    if not result:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return result

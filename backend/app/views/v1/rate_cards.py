from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.domain.schemas.rate_card_schemas import (
    CreateVersionRequest,
    RateCardResponse,
    RateCardSummary,
    RateCardUpdate,
)
from app.infrastructure.db.database import get_db
from app.viewmodels.rate_card_viewmodel import RateCardViewModel

router = APIRouter(prefix="/rate-cards", tags=["rate-cards"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> RateCardViewModel:
    return RateCardViewModel(request, db)


@router.get("/active", response_model=RateCardResponse)
async def get_active_rate_card(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: RateCardViewModel = Depends(get_vm),
):
    rc = await vm.get_active(agency_id)
    if not rc:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return rc


@router.get("", response_model=list[RateCardSummary])
async def list_rate_card_versions(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: RateCardViewModel = Depends(get_vm),
):
    return await vm.list_versions(agency_id)


@router.patch("/{rate_card_id}", response_model=RateCardResponse)
async def update_rate_card(
    rate_card_id: UUID,
    data: RateCardUpdate,
    vm: RateCardViewModel = Depends(get_vm),
):
    rc = await vm.update_rate_card(rate_card_id, data)
    if not rc:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return rc


@router.post("", response_model=RateCardResponse, status_code=status.HTTP_201_CREATED)
async def create_rate_card_version(
    data: CreateVersionRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: RateCardViewModel = Depends(get_vm),
):
    return await vm.create_version(agency_id, data)

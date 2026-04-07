from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.domain.schemas.agency_schemas import AgencyResponse, AgencyUpdate, OnboardingStepRequest
from app.infrastructure.db.database import get_db
from app.viewmodels.agency_viewmodel import AgencyViewModel

router = APIRouter(prefix="/agencies", tags=["agencies"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> AgencyViewModel:
    return AgencyViewModel(request, db)


@router.get("/me", response_model=AgencyResponse)
async def get_my_agency(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: AgencyViewModel = Depends(get_vm),
):
    agency = await vm.get_agency(agency_id)
    if not agency:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return agency


@router.patch("/me", response_model=AgencyResponse)
async def update_my_agency(
    data: AgencyUpdate,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: AgencyViewModel = Depends(get_vm),
):
    agency = await vm.update_agency(agency_id, data)
    if not agency:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return agency


@router.post("/me/onboarding", response_model=AgencyResponse)
async def onboarding_step(
    step_data: OnboardingStepRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: AgencyViewModel = Depends(get_vm),
):
    agency = await vm.process_onboarding_step(agency_id, step_data)
    if not agency:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return agency

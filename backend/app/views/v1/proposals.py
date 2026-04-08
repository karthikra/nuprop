from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.domain.schemas.proposal_schemas import (
    PreferencesUpdate,
    ProposalCreate,
    ProposalListItem,
    ProposalResponse,
    ProposalUpdate,
)
from app.infrastructure.db.database import get_db
from app.viewmodels.proposal_viewmodel import ProposalViewModel

router = APIRouter(prefix="/proposals", tags=["proposals"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> ProposalViewModel:
    return ProposalViewModel(request, db)


@router.get("", response_model=list[ProposalListItem])
async def list_proposals(
    proposal_status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ProposalViewModel = Depends(get_vm),
):
    return await vm.list_proposals(agency_id, proposal_status, skip, limit)


@router.post("", response_model=ProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_proposal(
    data: ProposalCreate,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ProposalViewModel = Depends(get_vm),
):
    proposal = await vm.create_proposal(agency_id, data)
    if not proposal:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return proposal


@router.get("/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ProposalViewModel = Depends(get_vm),
):
    proposal = await vm.get_proposal(proposal_id, agency_id)
    if not proposal:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return proposal


@router.patch("/{proposal_id}", response_model=ProposalResponse)
async def update_proposal(
    proposal_id: UUID,
    data: ProposalUpdate,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ProposalViewModel = Depends(get_vm),
):
    proposal = await vm.update_proposal(proposal_id, agency_id, data)
    if not proposal:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return proposal


@router.delete("/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proposal(
    proposal_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ProposalViewModel = Depends(get_vm),
):
    if not await vm.delete_proposal(proposal_id, agency_id):
        raise HTTPException(status_code=vm.status_code, detail=vm.error)


@router.patch("/{proposal_id}/preferences", response_model=ProposalResponse)
async def update_preferences(
    proposal_id: UUID,
    data: PreferencesUpdate,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ProposalViewModel = Depends(get_vm),
):
    proposal = await vm.update_preferences(proposal_id, agency_id, data)
    if not proposal:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return proposal

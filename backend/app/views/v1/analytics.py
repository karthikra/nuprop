from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.domain.schemas.analytics_schemas import (
    OverviewStatsResponse,
    ProposalAnalyticsListItem,
    ProposalAnalyticsResponse,
    VisitorSummaryResponse,
)
from app.infrastructure.db.database import get_db
from app.viewmodels.analytics_viewmodel import AnalyticsViewModel

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> AnalyticsViewModel:
    return AnalyticsViewModel(request, db)


@router.get("/overview", response_model=OverviewStatsResponse)
async def analytics_overview(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: AnalyticsViewModel = Depends(get_vm),
):
    return await vm.get_overview(agency_id)


@router.get("/proposals/{proposal_id}", response_model=ProposalAnalyticsResponse)
async def analytics_proposal_detail(
    proposal_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: AnalyticsViewModel = Depends(get_vm),
):
    result = await vm.get_proposal_analytics(proposal_id, agency_id)
    if not result:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return result


@router.get("/proposals/{proposal_id}/visitors", response_model=list[VisitorSummaryResponse])
async def analytics_proposal_visitors(
    proposal_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: AnalyticsViewModel = Depends(get_vm),
):
    result = await vm.get_visitors(proposal_id, agency_id)
    if result is None:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return result

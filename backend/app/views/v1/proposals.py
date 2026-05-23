from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
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
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.rate_card_excel_parser import MAX_BYTES, parse_and_extract
from app.viewmodels.proposal_viewmodel import ProposalViewModel
from app.viewmodels.rate_card_viewmodel import RateCardViewModel

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


@router.post("/{proposal_id}/rate-card-gaps/fill", status_code=200)
async def fill_rate_card_gaps(
    proposal_id: UUID,
    body: dict,
    request: Request,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    if not proposal.rate_card_gaps:
        raise HTTPException(status_code=400, detail="No rate-card gaps to fill")

    gaps = proposal.rate_card_gaps
    allowed_role_keys = set(gaps.get("missing_roles", []))
    allowed_offering_keys = set(gaps.get("missing_offerings", []))

    submitted_rates = body.get("hourly_rates") or {}
    submitted_offerings = body.get("offerings") or {}

    for k in submitted_rates:
        if k not in allowed_role_keys:
            raise HTTPException(status_code=400, detail=f"Role '{k}' is not in the detected gaps")
    for k in submitted_offerings:
        if k not in allowed_offering_keys:
            raise HTTPException(status_code=400, detail=f"Offering '{k}' is not in the detected gaps")

    rc_vm = RateCardViewModel(request, db)
    await rc_vm.add_missing_entries(
        agency_id=agency_id,
        hourly_rates=submitted_rates,
        offerings=submitted_offerings,
    )
    await proposal_repo.update(proposal_id, rate_card_gaps=None)
    await db.commit()

    pool = request.app.state.arq_pool
    await pool.enqueue_job(
        "run_research", str(proposal_id), _job_id=f"{proposal_id}:run_research"
    )
    return {"ok": True}


@router.post("/{proposal_id}/rate-card-gaps/skip", status_code=204)
async def skip_rate_card_gaps(
    proposal_id: UUID,
    request: Request,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    if not proposal.rate_card_gaps:
        # already cleared — idempotent
        return Response(status_code=204)

    await proposal_repo.update(proposal_id, rate_card_gaps=None)
    await db.commit()

    pool = request.app.state.arq_pool
    await pool.enqueue_job(
        "run_research", str(proposal_id), _job_id=f"{proposal_id}:run_research"
    )
    return Response(status_code=204)


@router.post("/{proposal_id}/rate-card-import", status_code=200)
async def import_rate_card_xlsx(
    proposal_id: UUID,
    file: UploadFile = File(...),
    request: Request = None,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_BYTES // (1024 * 1024)} MB limit")

    try:
        preview = await parse_and_extract(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not parse spreadsheet: {exc}")

    return preview  # NOT persisted — frontend must call /confirm with the (possibly edited) preview


@router.post("/{proposal_id}/rate-card-import/confirm", status_code=200)
async def confirm_rate_card_import(
    proposal_id: UUID,
    body: dict,
    request: Request,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    override = {
        "hourly_rates": body.get("hourly_rates") or {},
        "offerings": body.get("offerings") or {},
        "multipliers": body.get("multipliers") or {},
    }

    await proposal_repo.update(
        proposal_id,
        rate_card_override=override,
        rate_card_gaps=None,
    )
    await db.commit()

    await request.app.state.arq_pool.enqueue_job(
        "run_research", str(proposal_id),
        _job_id=f"{proposal_id}:run_research",
    )
    return {"ok": True}

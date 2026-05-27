from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
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
from app.infrastructure.db.models.proposal import Proposal
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.media import _s3
from app.services.media._common import (
    ALLOWED_MIMES,
    build_s3_key,
    ext_from_mime,
    new_asset_id,
    validate_upload,
)
from app.services.media.image_gen import generate_image
from app.services.media.section_assets import (
    append_asset_to_section,
    remove_asset_from_section,
    resign_assets,
)
from app.services.rate_card_excel_parser import MAX_BYTES, parse_and_extract
from app.services.sections import FACT_SECTIONS, SECTION_ORDER, SYNTHESIS_SECTIONS
from app.services.ai.section_facts import generate_fact_section
from app.services.ai.section_synthesis import generate_synthesis_section
from app.viewmodels.proposal_viewmodel import ProposalViewModel
from app.viewmodels.rate_card_viewmodel import RateCardViewModel


def _resign_response_sections(resp: ProposalResponse) -> ProposalResponse:
    """Return ``resp`` with every section's ``assets[].url`` freshly signed.

    Operates on the Pydantic response — never mutates the SA model (that would
    be persisted by ``get_db``'s on-exit commit).
    """
    for col in SECTION_ORDER:
        current = getattr(resp, col, None)
        if current is None or not current.get("assets"):
            continue
        setattr(resp, col, resign_assets(current, signer=_s3.generate_presigned_get))
    return resp


router = APIRouter(prefix="/proposals", tags=["proposals"])


class RateCardConfirmBody(BaseModel):
    hourly_rates: dict[str, int | float] = {}
    offerings: dict[str, dict] = {}
    multipliers: dict[str, int | float] = {}


class _FillOffering(BaseModel):
    name: str
    base_price: int


class RateCardFillBody(BaseModel):
    hourly_rates: dict[str, int | float] = {}
    offerings: dict[str, _FillOffering] = {}


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
    return _resign_response_sections(ProposalResponse.model_validate(proposal))


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
    return _resign_response_sections(ProposalResponse.model_validate(proposal))


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
    body: RateCardFillBody,
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

    submitted_rates = body.hourly_rates
    submitted_offerings = {k: v.model_dump() for k, v in body.offerings.items()}

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
    body: RateCardConfirmBody,
    request: Request,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    override = body.model_dump()
    # Normalize multipliers from flat {"key": value} to {"key": {"value": value}}
    # to match the shape CostModelBuilder reads from agency master rate cards.
    multipliers = override.get("multipliers") or {}
    normalized_multipliers: dict[str, dict] = {}
    for key, value in multipliers.items():
        if isinstance(value, dict):
            normalized_multipliers[key] = value
        else:
            normalized_multipliers[key] = {"value": value}
    override["multipliers"] = normalized_multipliers

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


# ── Section CRUD endpoints ────────────────────────────────────────────────────

class PatchSectionBody(BaseModel):
    content: str | None = None
    included: bool | None = None
    metadata: dict | None = None


class RefineSectionBody(BaseModel):
    instructions: str


class PresignAssetBody(BaseModel):
    kind: str
    filename: str
    content_type: str
    size: int = Field(gt=0)


class CommitAssetBody(BaseModel):
    asset_id: str
    s3_key: str
    kind: str
    content_type: str
    caption: str | None = None
    width: int | None = None
    height: int | None = None


class GenerateAssetBody(BaseModel):
    kind: str
    prompt: str = Field(min_length=1)


def _validate_section_type(section_type: str) -> None:
    if section_type not in SECTION_ORDER:
        raise HTTPException(status_code=400, detail=f"Unknown section type: {section_type}")


async def _resolve_proposal(repo: ProposalRepository, proposal_id: UUID, agency_id: UUID) -> Proposal:
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


def _resign_asset(asset: dict) -> dict:
    """Re-sign a single asset's ``url`` from its ``s3_key`` (returns a copy)."""
    return {**asset, "url": _s3.generate_presigned_get(asset["s3_key"])}


@router.patch("/{proposal_id}/sections/{section_type}", status_code=200)
async def patch_section(
    proposal_id: UUID,
    section_type: str,
    body: PatchSectionBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    current = getattr(proposal, section_type) or {
        "content": "", "assets": [], "included": True, "metadata": {}
    }
    updated = {**current}
    if body.content is not None:
        updated["content"] = body.content
    if body.included is not None:
        updated["included"] = body.included
    if body.metadata is not None:
        updated["metadata"] = body.metadata

    await repo.update(proposal_id, **{section_type: updated})
    await db.commit()
    return updated


@router.post("/{proposal_id}/sections/{section_type}/regenerate", status_code=200)
async def regenerate_section(
    proposal_id: UUID,
    section_type: str,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    new_payload = await _generate_section(proposal, section_type, refine_instructions=None, db=db)
    await repo.update(proposal_id, **{section_type: new_payload})
    await db.commit()
    return new_payload


@router.post("/{proposal_id}/sections/{section_type}/refine", status_code=200)
async def refine_section(
    proposal_id: UUID,
    section_type: str,
    body: RefineSectionBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    new_payload = await _generate_section(
        proposal, section_type, refine_instructions=body.instructions, db=db,
    )
    await repo.update(proposal_id, **{section_type: new_payload})
    await db.commit()
    return new_payload


# ── Section asset endpoints (S10: image only; S11 widens kind) ───────────────


@router.post(
    "/{proposal_id}/sections/{section_type}/assets/presign",
    status_code=200,
)
async def presign_asset(
    proposal_id: UUID,
    section_type: str,
    body: PresignAssetBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await _resolve_proposal(repo, proposal_id, agency_id)

    try:
        validate_upload(kind=body.kind, content_type=body.content_type, size=body.size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ext = ext_from_mime(body.content_type) or "bin"
    asset_id = new_asset_id()
    s3_key = build_s3_key(
        agency_id=str(proposal.agency_id),
        proposal_id=str(proposal.id),
        asset_id=asset_id,
        ext=ext,
    )
    upload_url = _s3.generate_presigned_put(
        key=s3_key,
        content_type=body.content_type,
        content_length=body.size,
    )
    return {"upload_url": upload_url, "s3_key": s3_key, "asset_id": asset_id}


@router.post(
    "/{proposal_id}/sections/{section_type}/assets/commit",
    status_code=200,
)
async def commit_asset(
    proposal_id: UUID,
    section_type: str,
    body: CommitAssetBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await _resolve_proposal(repo, proposal_id, agency_id)

    # ── Auth on the s3_key — it must belong to this proposal's prefix ────
    expected_prefix = f"{proposal.agency_id}/{proposal.id}/"
    if not body.s3_key.startswith(expected_prefix):
        raise HTTPException(
            status_code=400,
            detail="s3_key does not belong to this proposal",
        )

    # ── Kind / mime consistency check (presign already validated, but the
    # commit body is independent and may be malicious / out of sync) ─────
    if body.kind not in ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {body.kind}")
    if body.content_type not in ALLOWED_MIMES[body.kind]:
        raise HTTPException(
            status_code=400,
            detail=f"content_type {body.content_type!r} does not match kind {body.kind!r}",
        )
    # The s3_key must end with the canonical extension for body.content_type.
    expected_ext = ext_from_mime(body.content_type)
    if not expected_ext or not body.s3_key.endswith(f".{expected_ext}"):
        raise HTTPException(
            status_code=400,
            detail=f"s3_key extension does not match content_type {body.content_type!r}",
        )

    asset: dict = {
        "id": body.asset_id,
        "kind": body.kind,
        "s3_key": body.s3_key,
        "caption": body.caption,
        "ai_generated": False,
        "prompt": None,
        "provider": "upload",
        "width": body.width,
        "height": body.height,
        "duration_s": None,
        "poster_s3_key": None,
    }
    current = getattr(proposal, section_type)
    new_section = append_asset_to_section(current, asset)
    await repo.update(proposal_id, **{section_type: new_section})
    await db.commit()
    return _resign_asset(asset)


@router.post(
    "/{proposal_id}/sections/{section_type}/assets/generate",
    status_code=200,
)
async def generate_asset(
    proposal_id: UUID,
    section_type: str,
    body: GenerateAssetBody,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await _resolve_proposal(repo, proposal_id, agency_id)

    if body.kind != "image":
        raise HTTPException(
            status_code=400,
            detail=f"Generation for kind={body.kind!r} is not supported yet (S10 ships image only)",
        )

    try:
        asset = await generate_image(
            prompt=body.prompt,
            agency_id=str(proposal.agency_id),
            proposal_id=str(proposal.id),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Image generation failed: {e}") from e
    current = getattr(proposal, section_type)
    new_section = append_asset_to_section(current, asset)
    await repo.update(proposal_id, **{section_type: new_section})
    await db.commit()
    return _resign_asset(asset)


@router.delete(
    "/{proposal_id}/sections/{section_type}/assets/{asset_id}",
    status_code=204,
)
async def delete_asset(
    proposal_id: UUID,
    section_type: str,
    asset_id: str,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    _validate_section_type(section_type)
    repo = ProposalRepository(db)
    proposal = await _resolve_proposal(repo, proposal_id, agency_id)

    current = getattr(proposal, section_type)
    if not current or not current.get("assets"):
        raise HTTPException(status_code=404, detail="Asset not found")

    new_section, removed = remove_asset_from_section(current, asset_id=asset_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    # DB is source of truth — update + commit first; orphan S3 objects are
    # garbage-collected by the bucket lifecycle, but a missing-but-listed
    # asset shows up as a broken card to the user.
    await repo.update(proposal_id, **{section_type: new_section})
    await db.commit()
    await _s3.delete_object(removed["s3_key"])
    return Response(status_code=204)


async def _generate_section(
    proposal,
    section_type: str,
    refine_instructions: str | None,
    db: AsyncSession,
) -> dict:
    """Single-section dispatch shared by /regenerate and /refine."""
    from sqlalchemy import select
    from app.infrastructure.db.models.agency import Agency

    agency_row = await db.execute(select(Agency).where(Agency.id == proposal.agency_id))
    agency = agency_row.scalar_one()

    if section_type in FACT_SECTIONS:
        return await generate_fact_section(
            section_type=section_type,
            brief=proposal.brief or {},
            research=proposal.research,
            cost_model=proposal.cost_model or {},
            template_config=None,
            context_brief=proposal.context_brief,
            agency_name=agency.name,
            refine_instructions=refine_instructions,
        )
    # Synthesis section — rebuild pass1_sections dict from current proposal columns.
    # Include executive_summary AND fact sections (everything except the section being
    # regenerated, to avoid stale self-reference).
    pass1_sections = {
        s: getattr(proposal, s) or {}
        for s in SECTION_ORDER
        if s != section_type
    }
    return await generate_synthesis_section(
        section_type=section_type,
        brief=proposal.brief or {},
        pass1_sections=pass1_sections,
        context_brief=proposal.context_brief,
        agency_name=agency.name,
        refine_instructions=refine_instructions,
    )

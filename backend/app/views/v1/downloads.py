from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository

router = APIRouter(prefix="/dl", tags=["downloads"])


@router.get("/{proposal_id}/{filename}")
async def download_file(
    proposal_id: UUID,
    filename: str,
    agency_id: UUID = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Download a generated proposal file (DOCX, HTML, etc.)."""
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    # Validate filename to prevent path traversal
    safe_name = Path(filename).name
    file_path = Path("outputs") / str(proposal_id) / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".html": "text/html",
        ".pdf": "application/pdf",
        ".md": "text/markdown",
    }
    suffix = file_path.suffix.lower()
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=safe_name,
    )

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["proposal-site"])


@router.get("/p/{proposal_id}")
async def view_proposal_site(proposal_id: str):
    """Serve the interactive proposal site. Public — no auth required."""
    site_path = Path("outputs") / proposal_id / "site" / "index.html"
    if not site_path.exists():
        raise HTTPException(status_code=404, detail="Proposal site not found")
    return HTMLResponse(site_path.read_text(encoding="utf-8"))

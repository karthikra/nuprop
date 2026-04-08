from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.domain.schemas.client_schemas import ClientCreate, ClientResponse, ClientUpdate
from app.infrastructure.db.database import get_db
from app.viewmodels.client_viewmodel import ClientViewModel

router = APIRouter(prefix="/clients", tags=["clients"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> ClientViewModel:
    return ClientViewModel(request, db)


@router.get("", response_model=list[ClientResponse])
async def list_clients(
    q: str | None = None,
    industry: str | None = None,
    tag: str | None = None,
    skip: int = 0,
    limit: int = 50,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ClientViewModel = Depends(get_vm),
):
    return await vm.list_clients(agency_id, q, industry, tag, skip, limit)


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ClientViewModel = Depends(get_vm),
):
    return await vm.create_client(agency_id, data)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(client_id: UUID, vm: ClientViewModel = Depends(get_vm)):
    client = await vm.get_client(client_id)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: UUID,
    data: ClientUpdate,
    vm: ClientViewModel = Depends(get_vm),
):
    client = await vm.update_client(client_id, data)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(client_id: UUID, vm: ClientViewModel = Depends(get_vm)):
    if not await vm.delete_client(client_id):
        raise HTTPException(status_code=vm.status_code, detail=vm.error)


class ContextInput(BaseModel):
    raw_text: str


@router.post("/{client_id}/context", response_model=ClientResponse)
async def add_context(
    client_id: UUID,
    body: ContextInput,
    vm: ClientViewModel = Depends(get_vm),
):
    """Parse pasted text into structured context and merge into client profile."""
    client = await vm.get_client(client_id)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)

    from app.services.context_service import ContextService
    svc = ContextService()

    # Extract structured context from pasted text
    extraction = await svc.extract_context(body.raw_text)

    # Merge with existing context profile
    existing = client.context_profile or {}
    merged = await svc.merge_context(existing, extraction)

    # Save to client
    updated = await vm.update_client(client_id, ClientUpdate(context_profile=merged))  # type: ignore
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update context")
    return updated


@router.get("/{client_id}/context-brief")
async def get_context_brief(
    client_id: UUID,
    include_emails: bool = False,
    vm: ClientViewModel = Depends(get_vm),
    db: AsyncSession = Depends(get_db),
):
    """Generate a natural-language Context Brief. Optionally enriches with email data."""
    client = await vm.get_client(client_id)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)

    context_profile = client.context_profile or {}

    from app.services.context_service import ContextService
    svc = ContextService()

    email_count = 0
    if include_emails and client.contacts:
        try:
            from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository
            email_repo = EmailIndexRepository(db)
            domains = [
                c["email"].split("@")[-1].lower()
                for c in (client.contacts if isinstance(client.contacts, list) else [])
                if isinstance(c, dict) and c.get("email") and "@" in c["email"]
            ]
            if domains:
                emails = await email_repo.get_recent_for_domains(client.agency_id, domains, limit=20)
                email_count = len(emails)
                if emails:
                    email_dicts = [
                        {"summary": e.summary, "message_type": e.message_type, "sentiment": e.sentiment, "subject": e.subject, "date": str(e.date)}
                        for e in emails
                    ]
                    context_profile = await svc.enrich_context_with_emails(context_profile, email_dicts)
        except Exception:
            pass  # Don't let email enrichment failures block the brief

    if not context_profile:
        return {"brief": "", "has_context": False, "email_count": email_count}

    brief = await svc.generate_context_brief(client.name, context_profile)
    return {"brief": brief, "has_context": True, "email_count": email_count}

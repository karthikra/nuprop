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
    vm: ClientViewModel = Depends(get_vm),
):
    """Generate a natural-language Context Brief for this client."""
    client = await vm.get_client(client_id)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)

    if not client.context_profile:
        return {"brief": "", "has_context": False}

    from app.services.context_service import ContextService
    svc = ContextService()
    brief = await svc.generate_context_brief(client.name, client.context_profile)
    return {"brief": brief, "has_context": True}

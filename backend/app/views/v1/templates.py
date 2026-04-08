from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_agency_id
from app.domain.schemas.template_schemas import (
    CloneTemplateRequest,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)
from app.infrastructure.db.database import get_db
from app.viewmodels.template_viewmodel import TemplateViewModel

router = APIRouter(prefix="/templates", tags=["templates"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> TemplateViewModel:
    return TemplateViewModel(request, db)


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    agency_id: UUID = Depends(get_current_agency_id),
    vm: TemplateViewModel = Depends(get_vm),
):
    return await vm.list_templates(agency_id)


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: TemplateViewModel = Depends(get_vm),
):
    tmpl = await vm.get_template(template_id, agency_id)
    if not tmpl:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return tmpl


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: TemplateViewModel = Depends(get_vm),
):
    return await vm.create_template(agency_id, data)


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID,
    data: TemplateUpdate,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: TemplateViewModel = Depends(get_vm),
):
    tmpl = await vm.update_template(template_id, agency_id, data)
    if not tmpl:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return tmpl


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: TemplateViewModel = Depends(get_vm),
):
    if not await vm.delete_template(template_id, agency_id):
        raise HTTPException(status_code=vm.status_code, detail=vm.error)


@router.post("/{template_id}/clone", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def clone_template(
    template_id: UUID,
    data: CloneTemplateRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: TemplateViewModel = Depends(get_vm),
):
    tmpl = await vm.clone_template(template_id, agency_id, data)
    if not tmpl:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return tmpl

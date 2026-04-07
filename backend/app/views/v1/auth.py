from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.auth_schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.infrastructure.db.database import get_db
from app.core.deps import get_current_user
from app.infrastructure.db.models.user import User
from app.viewmodels.auth_viewmodel import AuthViewModel

router = APIRouter(prefix="/auth", tags=["auth"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> AuthViewModel:
    return AuthViewModel(request, db)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, vm: AuthViewModel = Depends(get_vm)):
    result = await vm.register(data)
    if not result:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return result


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, vm: AuthViewModel = Depends(get_vm)):
    result = await vm.login(data)
    if not result:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return result


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user

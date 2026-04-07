from __future__ import annotations

import re

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.domain.schemas.auth_schemas import LoginRequest, RegisterRequest, TokenResponse
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.user_repo import UserRepository
from app.viewmodels.shared.viewmodel import ViewModelBase


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower().strip())
    return re.sub(r"[-\s]+", "-", slug)


class AuthViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._user_repo: UserRepository | None = None
        self._agency_repo: AgencyRepository | None = None

    @property
    def user_repo(self) -> UserRepository:
        if not self._user_repo:
            self._user_repo = UserRepository(self._db)
        return self._user_repo

    @property
    def agency_repo(self) -> AgencyRepository:
        if not self._agency_repo:
            self._agency_repo = AgencyRepository(self._db)
        return self._agency_repo

    async def register(self, data: RegisterRequest) -> TokenResponse | None:
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            self.error = "Email already registered"
            self.status_code = 409
            return None

        agency = await self.agency_repo.create(
            name=data.agency_name,
            slug=_slugify(data.agency_name),
        )

        user = await self.user_repo.create(
            agency_id=agency.id,
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            is_owner=True,
        )

        token = create_access_token({"sub": str(user.id), "agency_id": str(agency.id)})
        self.status_code = 201
        return TokenResponse(
            access_token=token,
            user_id=user.id,
            agency_id=agency.id,
        )

    async def login(self, data: LoginRequest) -> TokenResponse | None:
        user = await self.user_repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            self.error = "Invalid email or password"
            self.status_code = 401
            return None

        token = create_access_token({"sub": str(user.id), "agency_id": str(user.agency_id)})
        self.status_code = 200
        return TokenResponse(
            access_token=token,
            user_id=user.id,
            agency_id=user.agency_id,
        )

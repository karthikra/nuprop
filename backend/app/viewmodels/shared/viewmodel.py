from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


class ViewModelBase:
    def __init__(self, request: Request, db: AsyncSession):
        self._request: Request = request
        self._db: AsyncSession = db
        self.status_code: int | None = None
        self.error: str | None = None
        self.message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_")
        }

    def to_response_dict(self) -> dict[str, Any]:
        d = self.to_dict()
        if self.error:
            return {"error": self.error, "status_code": self.status_code}
        return d

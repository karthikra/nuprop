from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GmailAuthUrlResponse(BaseModel):
    auth_url: str


class GmailCallbackRequest(BaseModel):
    code: str
    state: str = ""


class GmailStatusResponse(BaseModel):
    connected: bool = False
    configured: bool = False
    email: str | None = None
    last_sync: datetime | None = None
    email_count: int = 0


class GmailSyncResponse(BaseModel):
    new_emails: int = 0
    total_emails: int = 0
    domains_synced: list[str] = []
    duration_seconds: float = 0.0

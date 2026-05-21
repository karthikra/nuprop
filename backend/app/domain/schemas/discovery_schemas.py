from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DiscoveryRequest(BaseModel):
    lookback_days: Literal[30, 90, 365]


class TopSender(BaseModel):
    name: str
    email: str
    message_count: int


class Candidate(BaseModel):
    domain: str
    suggested_name: str
    message_count: int
    sender_count: int
    top_senders: list[TopSender]
    first_date: datetime
    last_date: datetime


class DiscoveryResponse(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list)
    excluded_existing: int = 0
    scanned_messages: int = 0
    duration_seconds: float = 0.0

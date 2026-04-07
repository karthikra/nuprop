from __future__ import annotations

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models.base import BaseModel, JSONColumn


class Agency(BaseModel):
    __tablename__ = "agencies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    colours: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    fonts: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    voice_profile: Mapped[str | None] = mapped_column(Text)
    default_terms: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    gst_rate: Mapped[float] = mapped_column(Float, default=0.18)
    payment_terms: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    settings: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    clients = relationship("Client", back_populates="agency", cascade="all, delete-orphan")
    proposals = relationship("Proposal", back_populates="agency", cascade="all, delete-orphan")
    rate_cards = relationship("RateCard", back_populates="agency", cascade="all, delete-orphan")
    templates = relationship("StrategyTemplate", back_populates="agency", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="agency", cascade="all, delete-orphan")

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.seed import seed_templates
from app.infrastructure.db.database import Base, async_session_factory, engine
from app.infrastructure.db.models import *  # noqa: F401, F403 — register all models
from app.views.v1.proposal_site import router as proposal_site_router
from app.views.v1.router import api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (dev only — production uses Alembic)
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Seed system templates
        async with async_session_factory() as db:
            count = await seed_templates(db)
            if count:
                await db.commit()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(proposal_site_router)  # Public route at /p/{id} — no API prefix

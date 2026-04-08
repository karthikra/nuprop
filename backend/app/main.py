from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

    # Seed system templates (idempotent — all environments)
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

# API routes
app.include_router(api_router)
app.include_router(proposal_site_router)

# Serve React SPA static files (production: built frontend copied into /app/static)
_static_dir = Path(__file__).parent.parent.parent / "static"
if _static_dir.exists() and (_static_dir / "index.html").exists():
    # Serve Vite build assets
    if (_static_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="static-assets")

    # SPA catch-all — serves index.html for all unmatched routes (React Router handles client-side routing)
    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        # Don't intercept API, proposal sites, or asset routes (already handled above)
        file_path = _static_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_static_dir / "index.html"))

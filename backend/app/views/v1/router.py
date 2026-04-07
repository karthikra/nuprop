from __future__ import annotations

from fastapi import APIRouter

from app.views.v1.agencies import router as agencies_router
from app.views.v1.auth import router as auth_router
from app.views.v1.chat import router as chat_router
from app.views.v1.clients import router as clients_router
from app.views.v1.downloads import router as downloads_router
from app.views.v1.health import router as health_router
from app.views.v1.proposals import router as proposals_router
from app.views.v1.track import router as track_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(agencies_router)
api_router.include_router(clients_router)
api_router.include_router(proposals_router)
api_router.include_router(chat_router)
api_router.include_router(downloads_router)
api_router.include_router(track_router)

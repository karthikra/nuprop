from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.infrastructure.db.database import get_db
from app.infrastructure.db.models.user import User

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id_raw = payload["sub"]
    result = await db.execute(select(User).where(User.id == user_id_raw, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_agency_id(user: User = Depends(get_current_user)) -> UUID:
    return user.agency_id


# ── M16-M20 hardening (S1) — service / vault / nonce-store providers ────────


@lru_cache(maxsize=1)
def get_token_vault() -> "TokenVault":
    """Process singleton. Reads ENCRYPTION_KEY from settings at first call.
    For tests, override via `app.dependency_overrides[get_token_vault]`."""
    from app.core.config import get_settings
    from app.infrastructure.security.token_vault import TokenVault
    return TokenVault(key=get_settings().ENCRYPTION_KEY)


@lru_cache(maxsize=1)
def get_context_service() -> "ContextService":
    """Process singleton. The service is stateless except for its
    AnthropicClient, which is itself process-singleton-safe."""
    from app.services.context_service import ContextService
    return ContextService()


@lru_cache(maxsize=1)
def get_nonce_store() -> "NonceStore":
    """Process singleton. Returns RedisNonceStore in production (REDIS_ENABLED
    and the ARQ Redis pool is alive on app.state), else InMemoryNonceStore for
    dev and tests."""
    from app.core.config import get_settings
    from app.infrastructure.security.oauth_state import InMemoryNonceStore, RedisNonceStore
    settings = get_settings()
    if not settings.REDIS_ENABLED:
        return InMemoryNonceStore()
    # Late import + lazy client construction so the import doesn't crash when
    # Redis isn't available. The client is reused.
    from redis.asyncio import Redis
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return RedisNonceStore(redis)

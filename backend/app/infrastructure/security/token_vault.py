"""Fernet-backed token vault for OAuth refresh / access tokens.

Fail-loud semantics:
- `encrypt()` and `decrypt()` raise TokenVaultError("not_configured") if no
  key was provided. There is NO silent fallback to plaintext. The startup
  validator in `app.main` ensures the production process never reaches a
  vault call without configuration.
- `decrypt()` catches `cryptography.fernet.InvalidToken` (corrupted ciphertext
  or wrong key after rotation) and re-raises as TokenVaultError("decrypt_failed").
  Callers map this to a "needs re-auth" surface.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.errors import TokenVaultError

logger = logging.getLogger(__name__)


class TokenVault:
    """Stateless Fernet wrapper. One instance per process is fine (the
    underlying Fernet object is cheap and thread-safe)."""

    def __init__(self, *, key: str) -> None:
        self._key = key or ""
        self._fernet: Fernet | None = (
            Fernet(self._key.encode()) if self._key else None
        )

    @property
    def is_configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        if self._fernet is None:
            logger.warning(
                "token_vault.encrypt called without ENCRYPTION_KEY configured",
                extra={"event": "security.token_vault.not_configured"},
            )
            raise TokenVaultError(
                code="not_configured",
                message="ENCRYPTION_KEY is empty; refusing to encrypt",
            )
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        if self._fernet is None:
            logger.warning(
                "token_vault.decrypt called without ENCRYPTION_KEY configured",
                extra={"event": "security.token_vault.not_configured"},
            )
            raise TokenVaultError(
                code="not_configured",
                message="ENCRYPTION_KEY is empty; refusing to decrypt",
            )
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            logger.warning(
                "token_vault.decrypt rejected an invalid ciphertext (decrypt_failed: rotated key or corruption)",
                extra={"event": "security.token_vault.decrypt_failed"},
            )
            raise TokenVaultError(
                code="decrypt_failed",
                message="ciphertext could not be decrypted; user must re-authorize",
                cause=exc,
            ) from exc

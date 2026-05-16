"""M16-M20-specific exception hierarchy. Used by the security layer
(`app.infrastructure.security`) and the connector viewmodel to surface
structured failures that route handlers can pattern-match on.

Every error carries a stable `code` string (machine-parseable) and a
human-readable `message`. Optionally wraps an underlying `cause` exception
so the original traceback is preserved for logging."""

from __future__ import annotations


class _StructuredError(Exception):
    """Base for S1 error classes. Carries code + message + optional cause."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause = cause


class TokenVaultError(_StructuredError):
    """Raised when token encryption / decryption fails or is not configured."""


class OAuthStateError(_StructuredError):
    """Raised when OAuth `state` verification fails (signature, expiry,
    provider mismatch, or replay)."""


class ConnectorAuthError(_StructuredError):
    """Raised when a connector's stored credentials are invalid or expired
    and the user must re-authorize."""


class ConnectorSyncError(_StructuredError):
    """Raised when a connector sync operation fails in a way the caller
    should surface (e.g., upstream API outage)."""

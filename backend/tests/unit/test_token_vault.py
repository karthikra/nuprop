"""Tests for the TokenVault — Fernet-backed encryption with fail-loud
semantics. No silent fallback to plaintext."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.errors import TokenVaultError
from app.infrastructure.security.token_vault import TokenVault


def _key() -> str:
    return Fernet.generate_key().decode()


def test_is_configured_true_when_key_present():
    vault = TokenVault(key=_key())
    assert vault.is_configured is True


def test_is_configured_false_when_key_empty():
    vault = TokenVault(key="")
    assert vault.is_configured is False


def test_encrypt_then_decrypt_roundtrips():
    vault = TokenVault(key=_key())
    plaintext = "refresh-token-1ya29Glorem"
    ciphertext = vault.encrypt(plaintext)
    assert ciphertext != plaintext
    assert vault.decrypt(ciphertext) == plaintext


def test_encrypt_without_key_raises_token_vault_error():
    vault = TokenVault(key="")
    with pytest.raises(TokenVaultError) as exc_info:
        vault.encrypt("anything")
    assert exc_info.value.code == "not_configured"


def test_decrypt_without_key_raises_token_vault_error():
    vault = TokenVault(key="")
    with pytest.raises(TokenVaultError) as exc_info:
        vault.decrypt("anything")
    assert exc_info.value.code == "not_configured"


def test_decrypt_of_garbage_raises_token_vault_error():
    vault = TokenVault(key=_key())
    with pytest.raises(TokenVaultError) as exc_info:
        vault.decrypt("not-a-valid-fernet-token")
    assert exc_info.value.code == "decrypt_failed"
    assert exc_info.value.cause is not None


def test_decrypt_with_wrong_key_raises_token_vault_error():
    vault1 = TokenVault(key=_key())
    vault2 = TokenVault(key=_key())
    ciphertext = vault1.encrypt("hello")
    with pytest.raises(TokenVaultError) as exc_info:
        vault2.decrypt(ciphertext)
    assert exc_info.value.code == "decrypt_failed"


def test_encrypt_emits_log_on_failure(caplog):
    vault = TokenVault(key="")
    with caplog.at_level("WARNING", logger="app.infrastructure.security.token_vault"):
        with pytest.raises(TokenVaultError):
            vault.encrypt("anything")
    assert any("not_configured" in rec.message or "ENCRYPTION_KEY" in rec.message for rec in caplog.records)


def test_decrypt_emits_log_on_invalid_token(caplog):
    vault = TokenVault(key=_key())
    with caplog.at_level("WARNING", logger="app.infrastructure.security.token_vault"):
        with pytest.raises(TokenVaultError):
            vault.decrypt("not-valid")
    assert any("decrypt_failed" in rec.message or "InvalidToken" in rec.message for rec in caplog.records)

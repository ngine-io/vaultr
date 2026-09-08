"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from vaultr.settings import Settings
from vaultr.vault import VaultService, max_vault_text_length


def get_vault_service(request: Request) -> VaultService:
    return request.app.state.vault_service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


VaultServiceDep = Annotated[VaultService, Depends(get_vault_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def enforce_max_length(secret: str, settings: Settings) -> None:
    """Reject oversized plaintext before it reaches the key derivation.

    Raises:
        HTTPException: 413 when the plaintext exceeds the configured limit.
    """
    if len(secret) > settings.max_secret_length:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Secret exceeds the maximum of {settings.max_secret_length} characters",
        )


def enforce_max_vault_text_length(vault_text: str, settings: Settings) -> None:
    """Reject oversized vault text before it reaches the key derivation.

    Raises:
        HTTPException: 413 when the vault string exceeds the derived limit.
    """
    limit = max_vault_text_length(settings.max_secret_length)
    if len(vault_text) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Vault string exceeds the maximum of {limit} characters",
        )

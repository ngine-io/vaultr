"""JSON API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from vaultr.dependencies import SettingsDep, VaultServiceDep, enforce_max_length
from vaultr.schemas import (
    EncryptIn,
    EncryptOut,
    ErrorOut,
    ProjectListOut,
    ProjectOut,
)
from vaultr.security import require_token
from vaultr.vault import InvalidVariableNameError, UnknownProjectError, to_yaml_snippet

router = APIRouter(
    prefix="/api/v1",
    tags=["api"],
    dependencies=[Depends(require_token)],
    responses={401: {"model": ErrorOut, "description": "Missing or invalid bearer token"}},
)


@router.get(
    "/projects",
    response_model=ProjectListOut,
    name="api-projects",
    summary="List configured projects",
)
async def list_projects(vault: VaultServiceDep) -> ProjectListOut:
    """Return the projects available for encryption. Passphrases are never exposed."""
    return ProjectListOut(
        projects=[
            ProjectOut(
                name=project.name,
                description=project.description,
                vault_id=project.vault_id,
            )
            for project in vault.projects
        ]
    )


@router.post(
    "/encrypt",
    response_model=EncryptOut,
    name="api-encrypt",
    summary="Encrypt a secret for a project",
    responses={
        404: {"model": ErrorOut, "description": "Unknown project"},
        413: {"model": ErrorOut, "description": "Secret too large"},
        422: {"model": ErrorOut, "description": "Invalid request body"},
    },
)
async def encrypt(
    payload: EncryptIn,
    vault: VaultServiceDep,
    settings: SettingsDep,
    response: Response,
) -> EncryptOut:
    """Encrypt ``secret`` with the passphrase configured for ``project``.

    The plaintext is encrypted verbatim: no trailing newline is added or removed.
    """
    enforce_max_length(payload.secret, settings)

    try:
        vault_text = vault.encrypt(payload.project, payload.secret)
    except UnknownProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    yaml_snippet = None
    if payload.variable_name:
        try:
            yaml_snippet = to_yaml_snippet(payload.variable_name, vault_text)
        except InvalidVariableNameError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    # The body carries ciphertext derived from a secret the caller supplied; keep it
    # out of every intermediate cache.
    response.headers["Cache-Control"] = "no-store"

    project = vault.get_project(payload.project)
    return EncryptOut(
        project=project.name,
        vault_id=project.vault_id,
        vault_text=vault_text,
        yaml_snippet=yaml_snippet,
    )

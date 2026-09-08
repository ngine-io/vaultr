"""Server rendered UI, progressively enhanced with htmx."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from vaultr.dependencies import SettingsDep, VaultServiceDep
from vaultr.metadata import (
    API_DOCS_PATH,
    DOCS_URL,
    LICENSE_NAME,
    LICENSE_URL,
    PROJECT_URL,
    __version__,
)
from vaultr.security import require_token
from vaultr.vault import (
    DecryptionFailedError,
    InvalidVariableNameError,
    NotVaultTextError,
    ReencryptNotAllowedError,
    UnknownProjectError,
    max_vault_text_length,
    to_yaml_snippet,
)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Footer values, identical on every page, so they are globals rather than something
# each handler has to remember to pass along.
templates.env.globals.update(
    version=__version__,
    api_docs_path=API_DOCS_PATH,
    project_url=PROJECT_URL,
    docs_url=DOCS_URL,
    license_name=LICENSE_NAME,
    license_url=LICENSE_URL,
)

router = APIRouter(tags=["web"], include_in_schema=False, dependencies=[Depends(require_token)])


def normalise_plaintext(value: str) -> str:
    """Clean up what a browser textarea submits.

    Browsers send ``\\r\\n`` line endings and users rarely intend the trailing
    newline the textarea leaves behind, so both are removed. The JSON API encrypts
    verbatim and applies neither.
    """
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


@router.get("/", response_class=HTMLResponse, name="index", summary="Encryption form")
async def index(request: Request, vault: VaultServiceDep, settings: SettingsDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "projects": vault.projects,
            "app_name": settings.app_name,
            "reencrypt_enabled": settings.reencrypt_enabled,
        },
    )


@router.post(
    "/encrypt", response_class=HTMLResponse, name="web-encrypt", summary="Encrypt a secret"
)
async def encrypt(
    request: Request,
    vault: VaultServiceDep,
    settings: SettingsDep,
    project: Annotated[str, Form()],
    secret: Annotated[str, Form()],
    variable_name: Annotated[str, Form()] = "",
) -> HTMLResponse:
    plaintext = normalise_plaintext(secret)
    context: dict[str, object] = {
        "projects": vault.projects,
        "app_name": settings.app_name,
        "reencrypt_enabled": settings.reencrypt_enabled,
        "selected_project": project,
        "variable_name": variable_name,
    }

    error: str | None = None
    vault_text: str | None = None
    yaml_snippet: str | None = None

    if not plaintext.strip():
        # Whitespace only is almost certainly an accidental submit; a real secret made
        # of nothing but spaces is not worth encrypting silently.
        error = "Enter a secret to encrypt."
    elif len(plaintext) > settings.max_secret_length:
        error = f"Secret exceeds the maximum of {settings.max_secret_length} characters."
    else:
        try:
            vault_text = vault.encrypt(project, plaintext)
            if variable_name:
                yaml_snippet = to_yaml_snippet(variable_name, vault_text)
        except UnknownProjectError:
            error = "Select a configured project."
        except InvalidVariableNameError as exc:
            vault_text = None
            error = str(exc)

    context |= {"error": error, "vault_text": vault_text, "yaml_snippet": yaml_snippet}

    # htmx swaps the result fragment in place; a browser without JavaScript posts the
    # form normally and gets the whole page back.
    name = "partials/result.html" if request.headers.get("HX-Request") else "index.html"
    response = templates.TemplateResponse(request=request, name=name, context=context)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/reencrypt",
    response_class=HTMLResponse,
    name="reencrypt-form",
    summary="Re-encryption form",
)
async def reencrypt_form(
    request: Request, vault: VaultServiceDep, settings: SettingsDep
) -> HTMLResponse:
    if not settings.reencrypt_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Re-encryption is disabled"
        )
    return templates.TemplateResponse(
        request=request,
        name="reencrypt.html",
        context={
            "projects": vault.projects,
            "app_name": settings.app_name,
            "reencrypt_enabled": True,
        },
    )


@router.post(
    "/reencrypt",
    response_class=HTMLResponse,
    name="web-reencrypt",
    summary="Re-encrypt a secret for another project",
)
async def reencrypt(
    request: Request,
    vault: VaultServiceDep,
    settings: SettingsDep,
    source_project: Annotated[str, Form()],
    target_project: Annotated[str, Form()],
    vault_text: Annotated[str, Form()],
    variable_name: Annotated[str, Form()] = "",
) -> HTMLResponse:
    if not settings.reencrypt_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Re-encryption is disabled"
        )

    context: dict[str, object] = {
        "projects": vault.projects,
        "app_name": settings.app_name,
        "reencrypt_enabled": True,
        "source_project": source_project,
        "selected_project": target_project,
        "variable_name": variable_name,
    }

    error: str | None = None
    vault_text_out: str | None = None
    yaml_snippet: str | None = None

    # Only line endings are normalised here; normalise_vault_text does the rest, since
    # the envelope has to survive a pasted YAML block either way.
    submitted = vault_text.replace("\r\n", "\n").replace("\r", "\n").strip()

    limit = max_vault_text_length(settings.max_secret_length)
    if not submitted:
        error = "Paste the encrypted vault string to re-encrypt."
    elif len(submitted) > limit:
        error = f"Vault string exceeds the maximum of {limit} characters."
    else:
        try:
            vault_text_out = vault.reencrypt(source_project, target_project, submitted)
            if variable_name:
                yaml_snippet = to_yaml_snippet(variable_name, vault_text_out)
        except UnknownProjectError:
            error = "Select a configured source and target project."
        except ReencryptNotAllowedError:
            error = (
                f"Re-encrypting from {source_project} to {target_project} is not allowed "
                "by the server configuration."
            )
        except NotVaultTextError:
            error = (
                "That does not look like an Ansible Vault string. Paste the whole "
                "$ANSIBLE_VAULT block, or the key: !vault | snippet."
            )
        except DecryptionFailedError:
            error = (
                f"The vault string could not be decrypted with the passphrase of "
                f"{source_project}. Is the source project correct?"
            )
        except InvalidVariableNameError as exc:
            vault_text_out = None
            error = str(exc)

    context |= {"error": error, "vault_text": vault_text_out, "yaml_snippet": yaml_snippet}

    name = "partials/result.html" if request.headers.get("HX-Request") else "reencrypt.html"
    response = templates.TemplateResponse(request=request, name=name, context=context)
    response.headers["Cache-Control"] = "no-store"
    return response

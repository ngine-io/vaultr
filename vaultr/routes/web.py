"""Server rendered UI, progressively enhanced with htmx."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from vaultr.dependencies import SettingsDep, VaultServiceDep
from vaultr.metadata import (
    DOCS_URL,
    LICENSE_NAME,
    LICENSE_URL,
    PROJECT_URL,
    __version__,
)
from vaultr.security import require_token
from vaultr.vault import InvalidVariableNameError, UnknownProjectError, to_yaml_snippet

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Footer values, identical on every page, so they are globals rather than something
# each handler has to remember to pass along.
templates.env.globals.update(
    version=__version__,
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
        context={"projects": vault.projects, "app_name": settings.app_name},
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

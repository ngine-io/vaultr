"""The interactive API documentation, served entirely from this origin.

FastAPI's own docs page loads Swagger UI from a CDN and starts it with an inline
script. The Content Security Policy blocks both, which left the page blank, so this
route renders a page that uses the copies ``make assets`` puts in ``static/``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from vaultr.dependencies import SettingsDep
from vaultr.metadata import API_DOCS_PATH
from vaultr.routes.web import templates

router = APIRouter(include_in_schema=False)


@router.get(API_DOCS_PATH, response_class=HTMLResponse, name="api_docs")
async def api_docs(request: Request, settings: SettingsDep) -> HTMLResponse:
    # Behind a proxy on a sub path the schema URL needs the prefix, as FastAPI's own
    # page does it.
    openapi_url = request.scope.get("root_path", "") + (request.app.openapi_url or "")
    return templates.TemplateResponse(
        request=request,
        name="api_docs.html",
        context={"app_name": settings.app_name, "openapi_url": openapi_url},
    )

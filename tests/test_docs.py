"""The interactive API docs page at /api."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from vaultr.app import create_app
from vaultr.settings import Settings


def assets(html: str) -> list[str]:
    return re.findall(r'(?:src|href)="([^"]+)"', html)


def test_docs_page_uses_only_same_origin_assets(client: TestClient) -> None:
    """The CSP allows only 'self', so a CDN asset would leave the page blank."""
    response = client.get("/api")
    assert response.status_code == 200
    assert assets(response.text) == [
        "/static/css/swagger-ui.css",
        "/static/js/swagger-ui-bundle.js",
        "/static/js/swagger-init.js",
    ]
    assert 'data-openapi-url="/api/openapi.json"' in response.text


def test_docs_page_has_no_inline_script(client: TestClient) -> None:
    """script-src 'self' blocks inline scripts; Swagger UI starts from swagger-init.js."""
    html = client.get("/api").text
    assert re.findall(r"<script(?![^>]*\ssrc=)[^>]*>", html) == []
    assert "<style" not in html


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/encrypt" in response.json()["paths"]


def test_docs_page_prefixes_the_root_path(settings: Settings) -> None:
    """Behind a proxy on a sub path, as the server passes it in the ASGI scope."""
    with TestClient(create_app(settings), root_path="/vaultr") as client:
        html = client.get("/api").text
    assert "/vaultr/static/js/swagger-init.js" in assets(html)
    assert 'data-openapi-url="/vaultr/api/openapi.json"' in html


def test_docs_can_be_disabled(config_file: Path) -> None:
    settings = Settings(config_file=config_file, api_tokens=[], docs_enabled=False, _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api").status_code == 404
        assert client.get("/api/openapi.json").status_code == 404

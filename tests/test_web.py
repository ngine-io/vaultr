"""HTML UI behaviour."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vaultr.metadata import __version__
from vaultr.routes.web import normalise_plaintext

from .conftest import PROD_PASSPHRASE
from .test_api import decrypt


def test_index_lists_the_configured_projects(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'value="prod-myproject"' in response.text
    assert 'value="test-myproject"' in response.text


def test_index_does_not_leak_a_passphrase(client: TestClient) -> None:
    assert PROD_PASSPHRASE not in client.get("/").text


def test_form_post_returns_the_full_page(client: TestClient) -> None:
    response = client.post("/encrypt", data={"project": "prod-myproject", "secret": "hunter2"})
    assert response.status_code == 200
    assert "<form" in response.text
    assert "$ANSIBLE_VAULT" in response.text


def test_htmx_post_returns_only_the_fragment(client: TestClient) -> None:
    response = client.post(
        "/encrypt",
        data={"project": "prod-myproject", "secret": "hunter2"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "<form" not in response.text
    assert "$ANSIBLE_VAULT" in response.text


def test_result_is_not_cached(client: TestClient) -> None:
    response = client.post("/encrypt", data={"project": "prod-myproject", "secret": "hunter2"})
    assert response.headers["cache-control"] == "no-store"


def test_unknown_project_renders_an_error(client: TestClient) -> None:
    response = client.post("/encrypt", data={"project": "absent", "secret": "hunter2"})
    assert response.status_code == 200
    assert "Select a configured project." in response.text
    assert "$ANSIBLE_VAULT" not in response.text


def test_blank_secret_renders_an_error(client: TestClient) -> None:
    response = client.post("/encrypt", data={"project": "prod-myproject", "secret": "  \n"})
    assert "Enter a secret to encrypt." in response.text


def test_invalid_variable_name_renders_an_error_without_a_result(client: TestClient) -> None:
    response = client.post(
        "/encrypt",
        data={"project": "prod-myproject", "secret": "hunter2", "variable_name": "bad name"},
    )
    assert "not a valid Ansible variable name" in response.text
    assert "$ANSIBLE_VAULT" not in response.text


def test_oversized_secret_renders_an_error(client: TestClient, settings) -> None:
    response = client.post(
        "/encrypt",
        data={"project": "prod-myproject", "secret": "x" * (settings.max_secret_length + 1)},
    )
    assert "exceeds the maximum" in response.text


def test_submitted_secret_is_not_echoed_into_the_form(client: TestClient) -> None:
    # Re-rendering the plaintext would put it in the browser's page cache and history.
    response = client.post("/encrypt", data={"project": "prod-myproject", "secret": "hunter2"})
    assert "hunter2" not in response.text


def test_browser_line_endings_survive_encryption(client: TestClient) -> None:
    response = client.post(
        "/encrypt",
        data={"project": "prod-myproject", "secret": "line one\r\nline two\r\n"},
        headers={"HX-Request": "true"},
    )
    vault_text = response.text.split(">", 1)[1]
    start = vault_text.index("$ANSIBLE_VAULT")
    vault_text = vault_text[start : vault_text.index("</textarea>", start)]
    assert decrypt(vault_text, PROD_PASSPHRASE) == "line one\nline two"


@pytest.mark.parametrize(
    ("submitted", "expected"),
    [
        ("hunter2", "hunter2"),
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("hunter2\r\n", "hunter2"),
        ("hunter2\n\n\n", "hunter2"),
        ("  spaced  ", "  spaced  "),
        ("\n", ""),
    ],
)
def test_normalise_plaintext(submitted: str, expected: str) -> None:
    assert normalise_plaintext(submitted) == expected


class TestFooter:
    """The footer must credit the source and the license on every page."""

    def test_links_to_the_repository(self, client: TestClient) -> None:
        assert 'href="https://github.com/ngine-io/vaultr"' in client.get("/").text

    def test_shows_the_license(self, client: TestClient) -> None:
        body = client.get("/").text
        assert "Apache-2.0" in body
        assert 'href="https://github.com/ngine-io/vaultr/blob/main/LICENSE"' in body

    def test_shows_the_running_version(self, client: TestClient) -> None:
        assert __version__ in client.get("/").text

    def test_external_links_cannot_reach_back(self, client: TestClient) -> None:
        # target="_blank" without rel="noopener" hands the opened tab a handle on
        # the page that just displayed a plaintext secret.
        body = client.get("/").text
        for chunk in body.split('target="_blank"')[1:]:
            assert 'rel="noopener noreferrer"' in chunk[:40]

    def test_footer_is_present_after_an_encryption(self, client: TestClient) -> None:
        response = client.post("/encrypt", data={"project": "prod-myproject", "secret": "hunter2"})
        assert "Apache-2.0" in response.text

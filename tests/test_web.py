"""HTML UI behaviour."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vaultr.app import create_app
from vaultr.metadata import __version__
from vaultr.routes.web import normalise_plaintext
from vaultr.settings import Settings
from vaultr.vault import max_vault_text_length

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


class TestWithoutBuiltAssets:
    """The UI must render before `make assets` has ever run.

    `vaultr/static/` is generated and not in version control, so a CI job that only
    installs Python has no stylesheet. The pages still have to render: the static
    route must exist so `url_for("static")` resolves, even with nothing behind it.
    """

    @pytest.fixture
    def no_assets_client(
        self, settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> Iterator[TestClient]:
        monkeypatch.setattr("vaultr.app.STATIC_DIR", tmp_path / "never-built")
        with TestClient(create_app(settings)) as client:
            yield client

    def test_index_still_renders(self, no_assets_client: TestClient) -> None:
        response = no_assets_client.get("/")
        assert response.status_code == 200
        assert 'value="prod-myproject"' in response.text

    def test_stylesheet_is_missing_rather_than_fatal(self, no_assets_client: TestClient) -> None:
        assert no_assets_client.get("/static/css/main.css").status_code == 404

    def test_encryption_still_works(self, no_assets_client: TestClient) -> None:
        response = no_assets_client.post(
            "/encrypt", data={"project": "prod-myproject", "secret": "hunter2"}
        )
        assert response.status_code == 200
        assert "$ANSIBLE_VAULT" in response.text


class TestStyling:
    """Markup the Tabler stylesheet depends on.

    Tabler is Bootstrap based, so components are class names on a fixed structure.
    These break silently: the page still renders, just unstyled.
    """

    def test_uses_tabler_layout(self, client: TestClient) -> None:
        body = client.get("/").text
        for chunk in ('class="page"', "page-wrapper", "page-body", "page-header"):
            assert chunk in body

    def test_uses_tabler_form_controls(self, client: TestClient) -> None:
        body = client.get("/").text
        for chunk in ("form-select", "form-control", "form-label", "btn btn-primary"):
            assert chunk in body

    def test_labels_are_bound_to_their_inputs(self, client: TestClient) -> None:
        # Tabler styles labels, but only a for/id pair makes them clickable.
        body = client.get("/").text
        for field in ("project", "secret", "variable_name"):
            assert f'for="{field}"' in body
            assert f'id="{field}"' in body

    def test_assets_are_root_relative(self, client: TestClient) -> None:
        # url_for returns an absolute URL; behind a TLS terminating proxy that would
        # emit http:// and be blocked as mixed content, so only the path is used.
        body = client.get("/").text
        assert "http://testserver/static" not in body
        assert 'href="/static/css/tabler.min.css"' in body

    def test_result_fragment_uses_tabler_markup(self, client: TestClient) -> None:
        response = client.post(
            "/encrypt",
            data={"project": "prod-myproject", "secret": "hunter2"},
            headers={"HX-Request": "true"},
        )
        assert 'class="card"' in response.text
        assert "form-control font-monospace" in response.text

    def test_error_uses_the_danger_alert(self, client: TestClient) -> None:
        response = client.post("/encrypt", data={"project": "absent", "secret": "hunter2"})
        assert 'class="alert alert-danger"' in response.text
        assert "alert-heading" in response.text


class TestThemeSwitch:
    """Light/dark switching, following Tabler's own conventions."""

    def test_theme_script_runs_immediately_after_body(self, client: TestClient) -> None:
        # Tabler requires it there, undeferred, or the page flashes the light theme
        # before switching to the stored one.
        body = client.get("/").text
        assert body.index("<body>") < body.index("tabler-theme.min.js")
        assert body.index("tabler-theme.min.js") < body.index('class="page"')

        tag = re.search(r"<script[^>]*tabler-theme[^>]*>", body)
        assert tag is not None
        assert "defer" not in tag.group(0)
        assert "async" not in tag.group(0)

    def test_offers_both_directions(self, client: TestClient) -> None:
        body = client.get("/").text
        assert 'data-set-theme="dark"' in body
        assert 'data-set-theme="light"' in body

    def test_only_the_opposite_switch_is_visible(self, client: TestClient) -> None:
        # Tabler hides `hide-theme-dark` while dark is active, and vice versa, so
        # exactly one of the two icons shows at a time.
        body = client.get("/").text
        assert "hide-theme-dark" in body
        assert "hide-theme-light" in body

    def test_switches_work_without_javascript(self, client: TestClient) -> None:
        # The links carry ?theme=, which Tabler's own script honours, so the toggle
        # degrades to a normal navigation if app.js fails to load.
        body = client.get("/").text
        assert "?theme=dark" in body
        assert "?theme=light" in body

    def test_theme_links_point_at_the_index(self, client: TestClient) -> None:
        # A relative ?theme= on the /encrypt result page would GET a POST-only route.
        response = client.post("/encrypt", data={"project": "prod-myproject", "secret": "x"})
        assert 'href="/?theme=dark"' in response.text


class TestReencryptPage:
    """The /reencrypt page moves a secret between projects."""

    def encrypt_for(self, client: TestClient, project: str, value: str = "hunter2") -> str:
        return client.post("/api/v1/encrypt", json={"project": project, "secret": value}).json()[
            "vault_text"
        ]

    def test_page_renders_both_selects(self, client: TestClient) -> None:
        body = client.get("/reencrypt").text
        assert 'id="source_project"' in body
        assert 'id="target_project"' in body
        assert 'id="vault_text"' in body

    def test_navbar_links_to_it(self, client: TestClient) -> None:
        assert 'href="/reencrypt"' in client.get("/").text

    def test_form_post_returns_the_full_page(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert response.status_code == 200
        assert "<form" in response.text
        assert "$ANSIBLE_VAULT" in response.text

    def test_htmx_post_returns_only_the_fragment(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
            headers={"HX-Request": "true"},
        )
        assert "<form" not in response.text
        assert "test-myproject" in response.text
        assert "prod-myproject" in response.text

    def test_result_decrypts_with_the_target_passphrase(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
            headers={"HX-Request": "true"},
        )
        body = response.text
        start = body.index("$ANSIBLE_VAULT")
        vault_text = body[start : body.index("</textarea>", start)]
        assert decrypt(vault_text, PROD_PASSPHRASE) == "hunter2"

    def test_result_is_not_cached(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert response.headers["cache-control"] == "no-store"

    def test_plaintext_is_never_rendered(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject", "top-secret-value")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert "top-secret-value" not in response.text

    def test_wrong_source_shows_a_helpful_error(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "prod-myproject")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert "Is the source project correct?" in response.text
        # No result card: the placeholder in the form also mentions $ANSIBLE_VAULT,
        # so the readonly output field is what proves nothing was produced.
        assert 'id="vault-text"' not in response.text

    def test_plain_text_input_shows_an_error(self, client: TestClient) -> None:
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": "not a vault string",
            },
        )
        assert "does not look like an Ansible Vault string" in response.text

    def test_blank_input_shows_an_error(self, client: TestClient) -> None:
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": "   \n",
            },
        )
        assert "Paste the encrypted vault string" in response.text

    def test_forbidden_target_shows_an_error(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "restricted")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "restricted",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert "is not allowed" in response.text

    def test_variable_name_returns_a_snippet(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
                "variable_name": "db_password",
            },
            headers={"HX-Request": "true"},
        )
        assert "db_password: !vault |" in response.text

    def test_invalid_variable_name_shows_an_error_without_a_result(
        self, client: TestClient
    ) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
                "variable_name": "bad name",
            },
        )
        assert "not a valid Ansible variable name" in response.text
        assert 'id="vault-text"' not in response.text

    def test_oversized_input_shows_an_error(self, client: TestClient, settings) -> None:
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": "x" * (max_vault_text_length(settings.max_secret_length) + 1),
            },
        )
        assert "exceeds the maximum" in response.text

    def test_unknown_project_shows_an_error(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = client.post(
            "/reencrypt",
            data={
                "source_project": "absent",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert "Select a configured source and target project." in response.text


class TestReencryptDisabledInTheUI:
    @pytest.fixture
    def disabled_client(self, config_file: Path) -> Iterator[TestClient]:
        settings = Settings(config_file=config_file, reencrypt_enabled=False, _env_file=None)
        with TestClient(create_app(settings)) as client:
            yield client

    def test_page_is_gone(self, disabled_client: TestClient) -> None:
        assert disabled_client.get("/reencrypt").status_code == 404

    def test_post_is_gone(self, disabled_client: TestClient) -> None:
        response = disabled_client.post(
            "/reencrypt",
            data={"source_project": "a", "target_project": "b", "vault_text": "x"},
        )
        assert response.status_code == 404

    def test_navbar_link_is_hidden(self, disabled_client: TestClient) -> None:
        assert 'href="/reencrypt"' not in disabled_client.get("/").text

"""JSON API behaviour."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vaultr.app import create_app
from vaultr.settings import Settings
from vaultr.vault import VaultLib, VaultSecret, max_vault_text_length

from .conftest import PROD_PASSPHRASE


def decrypt(vault_text: str, passphrase: str) -> str:
    lib = VaultLib(secrets=[("default", VaultSecret(passphrase.encode()))])
    return lib.decrypt(vault_text.encode()).decode()


def test_list_projects(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["projects"]]
    assert names == ["prod-myproject", "test-myproject", "labelled", "restricted", "sealed"]


def test_list_projects_never_returns_a_passphrase(client: TestClient) -> None:
    assert PROD_PASSPHRASE not in client.get("/api/v1/projects").text


def test_encrypt_round_trips(client: TestClient) -> None:
    response = client.post(
        "/api/v1/encrypt", json={"project": "prod-myproject", "secret": "hunter2"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "prod-myproject"
    assert body["yaml_snippet"] is None
    assert decrypt(body["vault_text"], PROD_PASSPHRASE) == "hunter2"


def test_encrypt_is_not_cached(client: TestClient) -> None:
    response = client.post(
        "/api/v1/encrypt", json={"project": "prod-myproject", "secret": "hunter2"}
    )
    assert response.headers["cache-control"] == "no-store"


def test_encrypt_preserves_the_plaintext_verbatim(client: TestClient) -> None:
    # Unlike the UI, the API neither normalises line endings nor strips newlines.
    plaintext = "line one\r\nline two\n"
    response = client.post(
        "/api/v1/encrypt", json={"project": "prod-myproject", "secret": plaintext}
    )
    assert decrypt(response.json()["vault_text"], PROD_PASSPHRASE) == plaintext


def test_encrypt_with_variable_name_returns_a_snippet(client: TestClient) -> None:
    response = client.post(
        "/api/v1/encrypt",
        json={"project": "prod-myproject", "secret": "hunter2", "variable_name": "db_password"},
    )
    assert response.json()["yaml_snippet"].startswith("db_password: !vault |")


def test_encrypt_rejects_an_invalid_variable_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/encrypt",
        json={"project": "prod-myproject", "secret": "hunter2", "variable_name": "not valid"},
    )
    assert response.status_code == 422


def test_encrypt_unknown_project(client: TestClient) -> None:
    response = client.post("/api/v1/encrypt", json={"project": "absent", "secret": "x"})
    assert response.status_code == 404


def test_encrypt_rejects_an_empty_secret(client: TestClient) -> None:
    response = client.post("/api/v1/encrypt", json={"project": "prod-myproject", "secret": ""})
    assert response.status_code == 422


def test_encrypt_rejects_unknown_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/encrypt",
        json={"project": "prod-myproject", "secret": "x", "vault_id": "sneaky"},
    )
    assert response.status_code == 422


def test_encrypt_rejects_an_oversized_secret(client: TestClient, settings) -> None:
    response = client.post(
        "/api/v1/encrypt",
        json={"project": "prod-myproject", "secret": "x" * (settings.max_secret_length + 1)},
    )
    assert response.status_code == 413


def test_no_decrypt_endpoint_exists(client: TestClient) -> None:
    # Decryption is deliberately not offered: users must not be able to read back
    # secrets they did not submit.
    paths = client.get(client.app.openapi_url).json()["paths"]
    assert not any("decrypt" in path for path in paths)


def test_security_headers_are_set(client: TestClient) -> None:
    headers = client.get("/api/v1/projects").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["projects"] == 5


class TestAuthentication:
    def test_api_requires_a_token_when_configured(self, auth_client: TestClient) -> None:
        assert auth_client.get("/api/v1/projects").status_code == 401

    def test_wrong_token_is_rejected(self, auth_client: TestClient) -> None:
        response = auth_client.get("/api/v1/projects", headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401

    def test_correct_token_is_accepted(self, auth_client: TestClient) -> None:
        response = auth_client.get(
            "/api/v1/projects", headers={"Authorization": "Bearer s3cr3t-token"}
        )
        assert response.status_code == 200

    def test_ui_requires_a_token_too(self, auth_client: TestClient) -> None:
        assert auth_client.get("/").status_code == 401

    def test_health_stays_open_for_probes(self, auth_client: TestClient) -> None:
        assert auth_client.get("/healthz").status_code == 200

    def test_no_auth_configured_allows_everything(self, client: TestClient) -> None:
        assert client.get("/api/v1/projects").status_code == 200


class TestReencrypt:
    """POST /api/v1/reencrypt moves a secret between project passphrases."""

    def encrypt_for(self, client: TestClient, project: str, secret: str = "hunter2") -> str:
        response = client.post("/api/v1/encrypt", json={"project": project, "secret": secret})
        return response.json()["vault_text"]

    def reencrypt(self, client: TestClient, **payload: object):
        return client.post("/api/v1/reencrypt", json=payload)

    def test_round_trips_into_the_target_project(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=original,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["source_project"] == "test-myproject"
        assert body["target_project"] == "prod-myproject"
        assert decrypt(body["vault_text"], PROD_PASSPHRASE) == "hunter2"

    def test_never_returns_the_plaintext(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject", "top-secret-value")
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=original,
        )
        assert "top-secret-value" not in response.text

    def test_is_not_cached(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=original,
        )
        assert response.headers["cache-control"] == "no-store"

    def test_accepts_a_pasted_yaml_snippet(self, client: TestClient) -> None:
        encrypted = client.post(
            "/api/v1/encrypt",
            json={"project": "test-myproject", "secret": "hunter2", "variable_name": "db_pw"},
        ).json()
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=encrypted["yaml_snippet"],
        )
        assert response.status_code == 200
        assert decrypt(response.json()["vault_text"], PROD_PASSPHRASE) == "hunter2"

    def test_variable_name_returns_a_snippet(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=original,
            variable_name="db_password",
        )
        assert response.json()["yaml_snippet"].startswith("db_password: !vault |")

    def test_reports_the_target_vault_id(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "prod-myproject")
        response = self.reencrypt(
            client,
            source_project="prod-myproject",
            target_project="labelled",
            vault_text=original,
        )
        assert response.json()["vault_id"] == "labelled"

    def test_wrong_source_project_is_422(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "prod-myproject")
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=original,
        )
        assert response.status_code == 422
        assert "could not be decrypted" in response.json()["detail"]

    def test_plain_text_input_is_422(self, client: TestClient) -> None:
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text="not a vault string",
        )
        assert response.status_code == 422

    def test_unknown_project_is_404(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = self.reencrypt(
            client, source_project="nope", target_project="prod-myproject", vault_text=original
        )
        assert response.status_code == 404

    def test_forbidden_target_is_403(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "restricted")
        response = self.reencrypt(
            client,
            source_project="restricted",
            target_project="prod-myproject",
            vault_text=original,
        )
        assert response.status_code == 403
        assert "not allowed" in response.json()["detail"]

    def test_allowed_target_still_works(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "restricted")
        response = self.reencrypt(
            client,
            source_project="restricted",
            target_project="test-myproject",
            vault_text=original,
        )
        assert response.status_code == 200

    def test_invalid_variable_name_is_422(self, client: TestClient) -> None:
        original = self.encrypt_for(client, "test-myproject")
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=original,
            variable_name="not valid",
        )
        assert response.status_code == 422
        assert "not a valid Ansible variable name" in response.json()["detail"]

    def test_rejects_unknown_fields(self, client: TestClient) -> None:
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text="x",
            sneaky="value",
        )
        assert response.status_code == 422

    def test_oversized_input_is_413(self, client: TestClient, settings) -> None:
        oversized = "x" * (max_vault_text_length(settings.max_secret_length) + 1)
        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=oversized,
        )
        assert response.status_code == 413

    def test_a_vault_string_of_a_max_size_secret_is_accepted(
        self, client: TestClient, settings
    ) -> None:
        # A vault string is several times larger than the plaintext it encodes, so
        # bounding it by the plaintext limit would reject a legitimate secret.
        secret = "x" * (settings.max_secret_length // 2)
        original = self.encrypt_for(client, "test-myproject", secret)
        assert len(original) > settings.max_secret_length

        response = self.reencrypt(
            client,
            source_project="test-myproject",
            target_project="prod-myproject",
            vault_text=original,
        )
        assert response.status_code == 200
        assert decrypt(response.json()["vault_text"], PROD_PASSPHRASE) == secret

    def test_requires_a_token_when_configured(self, auth_client: TestClient) -> None:
        response = auth_client.post("/api/v1/reencrypt", json={})
        assert response.status_code == 401

    def test_projects_expose_their_reencrypt_policy(self, client: TestClient) -> None:
        projects = {p["name"]: p for p in client.get("/api/v1/projects").json()["projects"]}
        assert projects["prod-myproject"]["reencrypt_targets"] is None
        assert projects["restricted"]["reencrypt_targets"] == ["test-myproject"]
        assert projects["sealed"]["reencrypt_targets"] == []


class TestReencryptDisabled:
    def test_endpoint_is_403_when_turned_off(self, config_file) -> None:
        settings = Settings(config_file=config_file, reencrypt_enabled=False, _env_file=None)
        with TestClient(create_app(settings)) as client:
            response = client.post(
                "/api/v1/reencrypt",
                json={
                    "source_project": "test-myproject",
                    "target_project": "prod-myproject",
                    "vault_text": "$ANSIBLE_VAULT;1.1;AES256\n6430",
                },
            )
            assert response.status_code == 403

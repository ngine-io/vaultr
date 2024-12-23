"""JSON API behaviour."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vaultr.vault import VaultLib, VaultSecret

from .conftest import PROD_PASSPHRASE


def decrypt(vault_text: str, passphrase: str) -> str:
    lib = VaultLib(secrets=[("default", VaultSecret(passphrase.encode()))])
    return lib.decrypt(vault_text.encode()).decode()


def test_list_projects(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["projects"]]
    assert names == ["prod-myproject", "test-myproject", "labelled"]


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
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("decrypt" in path for path in paths)


def test_security_headers_are_set(client: TestClient) -> None:
    headers = client.get("/api/v1/projects").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["projects"] == 3


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

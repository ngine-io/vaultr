"""MCP server behaviour.

The tools are exercised through a real MCP client connected to the server in process,
so the assertions cover the schemas and error results an agent actually sees.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
import pytest
from ansible.parsing.vault import VaultLib, VaultSecret
from fastapi.testclient import TestClient
from mcp import Client

from vaultr.app import create_app
from vaultr.config import load_config
from vaultr.mcp_server import build_mcp_server
from vaultr.settings import Settings
from vaultr.vault import VaultService, max_vault_text_length

from .conftest import PROD_PASSPHRASE, TEST_PASSPHRASE

MAX_SECRET_LENGTH = 128


@pytest.fixture
def server(config_file: Path):
    vault = VaultService.from_config(load_config(config_file))
    return build_mcp_server(lambda: vault, max_secret_length=MAX_SECRET_LENGTH)


def call(server, name: str, arguments: dict[str, Any] | None = None):
    """Run one tool call against the server through a real MCP client."""

    async def run():
        async with Client(server) as client:
            return await client.call_tool(name, arguments or {})

    return anyio.run(run)


def list_tools(server):
    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    return anyio.run(run).tools


def decrypt(vault_text: str, passphrase: str) -> str:
    lib = VaultLib(secrets=[("default", VaultSecret(passphrase.encode()))])
    return lib.decrypt(vault_text.encode()).decode()


def text_of(result) -> str:
    return " ".join(block.text for block in result.content if block.type == "text")


class TestToolSurface:
    def test_exposes_exactly_the_expected_tools(self, server) -> None:
        assert sorted(t.name for t in list_tools(server)) == [
            "encrypt_secret",
            "list_vault_projects",
            "reencrypt_secret",
        ]

    def test_no_decrypt_tool_is_exposed(self, server) -> None:
        # An agent must not be able to read back a secret it did not submit.
        assert not any("decrypt" in t.name for t in list_tools(server))

    def test_tools_are_annotated_as_closed_world(self, server) -> None:
        for tool in list_tools(server):
            assert tool.annotations is not None
            assert tool.annotations.open_world_hint is False
            assert tool.annotations.destructive_hint is False

    def test_listing_is_marked_read_only(self, server) -> None:
        listing = next(t for t in list_tools(server) if t.name == "list_vault_projects")
        assert listing.annotations.read_only_hint is True

    def test_encryption_is_not_marked_idempotent(self, server) -> None:
        # It is salted: the same input yields a different vault string each call.
        encrypt = next(t for t in list_tools(server) if t.name == "encrypt_secret")
        assert encrypt.annotations.idempotent_hint is False

    def test_encrypt_declares_its_arguments(self, server) -> None:
        encrypt = next(t for t in list_tools(server) if t.name == "encrypt_secret")
        properties = encrypt.input_schema["properties"]
        assert set(properties) == {"project", "secret", "variable_name"}
        assert encrypt.input_schema["required"] == ["project", "secret"]


class TestListProjects:
    def test_returns_the_configured_projects(self, server) -> None:
        result = call(server, "list_vault_projects")
        names = [p["name"] for p in result.structured_content["projects"]]
        assert names == ["prod-myproject", "test-myproject", "labelled", "restricted", "sealed"]

    def test_never_returns_a_passphrase(self, server) -> None:
        assert PROD_PASSPHRASE not in str(call(server, "list_vault_projects").structured_content)


class TestEncrypt:
    def test_round_trips_through_ansible(self, server) -> None:
        result = call(server, "encrypt_secret", {"project": "prod-myproject", "secret": "hunter2"})
        assert result.is_error is False
        assert decrypt(result.structured_content["vault_text"], PROD_PASSPHRASE) == "hunter2"

    def test_encrypts_verbatim(self, server) -> None:
        plaintext = "line one\nline two\n"
        result = call(server, "encrypt_secret", {"project": "prod-myproject", "secret": plaintext})
        assert decrypt(result.structured_content["vault_text"], PROD_PASSPHRASE) == plaintext

    def test_variable_name_yields_a_yaml_snippet(self, server) -> None:
        result = call(
            server,
            "encrypt_secret",
            {"project": "prod-myproject", "secret": "hunter2", "variable_name": "db_password"},
        )
        assert result.structured_content["yaml_snippet"].startswith("db_password: !vault |")

    def test_snippet_is_absent_without_a_variable_name(self, server) -> None:
        result = call(server, "encrypt_secret", {"project": "prod-myproject", "secret": "x"})
        assert result.structured_content["yaml_snippet"] is None

    def test_reports_the_vault_id(self, server) -> None:
        result = call(server, "encrypt_secret", {"project": "labelled", "secret": "x"})
        assert result.structured_content["vault_id"] == "labelled"


class TestErrors:
    """Anticipated failures must reach the agent with enough detail to retry."""

    def test_unknown_project_lists_the_valid_ones(self, server) -> None:
        result = call(server, "encrypt_secret", {"project": "nope", "secret": "x"})
        assert result.is_error is True
        message = text_of(result)
        assert "unknown project 'nope'" in message
        assert "prod-myproject" in message

    def test_empty_secret(self, server) -> None:
        result = call(server, "encrypt_secret", {"project": "prod-myproject", "secret": ""})
        assert result.is_error is True
        assert "must not be empty" in text_of(result)

    def test_oversized_secret(self, server) -> None:
        result = call(
            server,
            "encrypt_secret",
            {"project": "prod-myproject", "secret": "x" * (MAX_SECRET_LENGTH + 1)},
        )
        assert result.is_error is True
        assert "exceeds the maximum" in text_of(result)

    def test_invalid_variable_name(self, server) -> None:
        result = call(
            server,
            "encrypt_secret",
            {"project": "prod-myproject", "secret": "x", "variable_name": "bad name"},
        )
        assert result.is_error is True
        assert "not a valid Ansible variable name" in text_of(result)

    def test_missing_argument_is_reported(self, server) -> None:
        result = call(server, "encrypt_secret", {"project": "prod-myproject"})
        assert result.is_error is True

    def test_a_failure_never_leaks_the_passphrase(self, server) -> None:
        result = call(server, "encrypt_secret", {"project": "nope", "secret": "x"})
        assert PROD_PASSPHRASE not in text_of(result)


class TestMounting:
    """The endpoint is mounted on the service and shares its bearer token."""

    def test_requires_a_token_when_one_is_configured(self, auth_client: TestClient) -> None:
        response = auth_client.post("/mcp/", json={})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_a_valid_token_gets_past_the_guard(self, auth_client: TestClient) -> None:
        response = auth_client.post(
            "/mcp/", json={}, headers={"Authorization": "Bearer s3cr3t-token"}
        )
        assert response.status_code != 401

    def test_mounted_by_default(self, client: TestClient) -> None:
        assert client.post("/mcp/", json={}).status_code != 404

    def test_can_be_disabled(self, config_file: Path) -> None:
        settings = Settings(config_file=config_file, mcp_enabled=False, _env_file=None)
        with TestClient(create_app(settings)) as client:
            assert client.post("/mcp/", json={}).status_code == 404


class TestReencryptTool:
    """`reencrypt_secret` moves a secret between project passphrases."""

    def encrypted_for(self, server, project: str, secret: str = "hunter2") -> str:
        result = call(server, "encrypt_secret", {"project": project, "secret": secret})
        return result.structured_content["vault_text"]

    def test_is_exposed(self, server) -> None:
        assert "reencrypt_secret" in [t.name for t in list_tools(server)]

    def test_declares_its_arguments(self, server) -> None:
        tool = next(t for t in list_tools(server) if t.name == "reencrypt_secret")
        assert set(tool.input_schema["properties"]) == {
            "source_project",
            "target_project",
            "vault_text",
            "variable_name",
        }
        assert tool.input_schema["required"] == ["source_project", "target_project", "vault_text"]

    def test_is_annotated_as_non_destructive_and_closed_world(self, server) -> None:
        tool = next(t for t in list_tools(server) if t.name == "reencrypt_secret")
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.open_world_hint is False
        # Salted, so the same input yields a different vault string each call.
        assert tool.annotations.idempotent_hint is False

    def test_moves_a_secret_between_projects(self, server) -> None:
        original = self.encrypted_for(server, "test-myproject")
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert result.is_error is False
        body = result.structured_content
        assert body["source_project"] == "test-myproject"
        assert body["target_project"] == "prod-myproject"
        assert decrypt(body["vault_text"], PROD_PASSPHRASE) == "hunter2"

    def test_never_returns_the_plaintext(self, server) -> None:
        original = self.encrypted_for(server, "test-myproject", "top-secret-value")
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert "top-secret-value" not in str(result.structured_content)
        assert "top-secret-value" not in text_of(result)

    def test_accepts_a_pasted_yaml_snippet(self, server) -> None:
        encrypted = call(
            server,
            "encrypt_secret",
            {"project": "test-myproject", "secret": "hunter2", "variable_name": "db_pw"},
        ).structured_content
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": encrypted["yaml_snippet"],
            },
        )
        assert decrypt(result.structured_content["vault_text"], PROD_PASSPHRASE) == "hunter2"

    def test_variable_name_yields_a_snippet(self, server) -> None:
        original = self.encrypted_for(server, "test-myproject")
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
                "variable_name": "db_password",
            },
        )
        assert result.structured_content["yaml_snippet"].startswith("db_password: !vault |")

    def test_reports_the_target_vault_id(self, server) -> None:
        original = self.encrypted_for(server, "prod-myproject")
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "prod-myproject",
                "target_project": "labelled",
                "vault_text": original,
            },
        )
        assert result.structured_content["vault_id"] == "labelled"

    def test_policy_is_visible_to_the_agent(self, server) -> None:
        # The agent needs to see where it may move a secret before it tries.
        projects = call(server, "list_vault_projects").structured_content["projects"]
        by_name = {p["name"]: p["reencrypt_targets"] for p in projects}
        assert by_name["prod-myproject"] is None
        assert by_name["restricted"] == ["test-myproject"]
        assert by_name["sealed"] == []


class TestReencryptToolErrors:
    """Every refusal must tell the agent enough to correct itself."""

    def encrypted_for(self, server, project: str) -> str:
        return call(
            server, "encrypt_secret", {"project": project, "secret": "hunter2"}
        ).structured_content["vault_text"]

    def test_wrong_source_project(self, server) -> None:
        original = self.encrypted_for(server, "prod-myproject")
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert result.is_error is True
        assert "source_project" in text_of(result)

    def test_not_vault_text(self, server) -> None:
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": "plain text",
            },
        )
        assert result.is_error is True
        assert "not an Ansible Vault string" in text_of(result)

    def test_forbidden_target_names_the_setting(self, server) -> None:
        original = self.encrypted_for(server, "restricted")
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "restricted",
                "target_project": "prod-myproject",
                "vault_text": original,
            },
        )
        assert result.is_error is True
        assert "not allowed" in text_of(result)
        assert "reencrypt_targets" in text_of(result)

    def test_unknown_project_lists_the_valid_ones(self, server) -> None:
        original = self.encrypted_for(server, "test-myproject")
        result = call(
            server,
            "reencrypt_secret",
            {"source_project": "nope", "target_project": "prod-myproject", "vault_text": original},
        )
        assert result.is_error is True
        assert "prod-myproject" in text_of(result)

    def test_empty_vault_text(self, server) -> None:
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": "",
            },
        )
        assert result.is_error is True
        assert "must not be empty" in text_of(result)

    def test_oversized_input(self, server) -> None:
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": "x" * (max_vault_text_length(MAX_SECRET_LENGTH) + 1),
            },
        )
        assert result.is_error is True
        assert "exceeds the maximum" in text_of(result)

    def test_invalid_variable_name(self, server) -> None:
        original = self.encrypted_for(server, "test-myproject")
        result = call(
            server,
            "reencrypt_secret",
            {
                "source_project": "test-myproject",
                "target_project": "prod-myproject",
                "vault_text": original,
                "variable_name": "bad name",
            },
        )
        assert result.is_error is True
        assert "not a valid Ansible variable name" in text_of(result)

    def test_a_failure_never_leaks_a_passphrase(self, server) -> None:
        result = call(
            server,
            "reencrypt_secret",
            {"source_project": "nope", "target_project": "prod-myproject", "vault_text": "x"},
        )
        assert PROD_PASSPHRASE not in text_of(result)
        assert TEST_PASSPHRASE not in text_of(result)


class TestReencryptToolDisabled:
    """A disabled instance must not advertise a tool that would always fail."""

    @pytest.fixture
    def disabled_server(self, config_file: Path):
        vault = VaultService.from_config(load_config(config_file))
        return build_mcp_server(
            lambda: vault, max_secret_length=MAX_SECRET_LENGTH, reencrypt_enabled=False
        )

    def test_tool_is_absent(self, disabled_server) -> None:
        assert [t.name for t in list_tools(disabled_server)] == [
            "list_vault_projects",
            "encrypt_secret",
        ]

    def test_calling_it_fails(self, disabled_server) -> None:
        result = call(
            disabled_server,
            "reencrypt_secret",
            {"source_project": "a", "target_project": "b", "vault_text": "x"},
        )
        assert result.is_error is True

    def test_encryption_still_works(self, disabled_server) -> None:
        result = call(
            disabled_server, "encrypt_secret", {"project": "prod-myproject", "secret": "hunter2"}
        )
        assert result.is_error is False

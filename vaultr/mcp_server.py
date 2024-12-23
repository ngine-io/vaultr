"""MCP server exposing the encryption API to agents.

Mounted into the FastAPI application at ``/mcp`` and backed by the same
:class:`~vaultr.vault.VaultService`, so an agent gets exactly what the HTTP API
offers and the vault passphrases never leave the process.

The module is named ``mcp_server`` rather than ``mcp`` so it cannot be confused with
the ``mcp`` package it imports.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from vaultr.metadata import PROJECT_URL, __version__
from vaultr.schemas import EncryptOut, ProjectListOut, ProjectOut
from vaultr.vault import (
    InvalidVariableNameError,
    UnknownProjectError,
    VaultService,
    to_yaml_snippet,
)

INSTRUCTIONS = f"""
Vaultr encrypts a secret into an Ansible Vault string using a passphrase held by the
server. Call `list_vault_projects` to see which projects are available, then
`encrypt_secret` with the project the secret belongs to.

The passphrases are never exposed and there is no way to decrypt: this server can only
turn plaintext into a vault string. The result is safe to write into a Git repository.

Documentation: {PROJECT_URL}
""".strip()

ENCRYPT_DESCRIPTION = """
Encrypt a secret into an Ansible Vault string for one project.

The plaintext is encrypted verbatim, so strip any trailing newline you do not want
inside the encrypted value. Pass `variable_name` to also get a ready to paste
`name: !vault |` YAML block for group_vars or host_vars.

Every call produces a different vault string even for the same input, because the
encryption is salted. Do not call this repeatedly expecting a stable result, and do not
re-encrypt a value that is already an $ANSIBLE_VAULT string.
""".strip()


def build_mcp_server(
    get_vault_service: Callable[[], VaultService],
    *,
    max_secret_length: int,
    app_name: str = "Vaultr",
) -> MCPServer:
    """Create the MCP server.

    The vault service is resolved lazily through ``get_vault_service`` because the
    configuration is loaded during application startup, after this server is built and
    mounted.
    """
    server: MCPServer = MCPServer(
        name=app_name,
        title=f"{app_name} — Ansible Vault encryption",
        version=__version__,
        instructions=INSTRUCTIONS,
        website_url=PROJECT_URL,
    )

    @server.tool(
        name="list_vault_projects",
        title="List Ansible Vault projects",
        description=(
            "List the projects this server can encrypt for. Each project has its own "
            "Ansible Vault passphrase, which is never returned."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def list_vault_projects() -> ProjectListOut:
        vault = get_vault_service()
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

    @server.tool(
        name="encrypt_secret",
        title="Encrypt a secret",
        description=ENCRYPT_DESCRIPTION,
        annotations=ToolAnnotations(
            read_only_hint=False,
            # Nothing is stored or overwritten; the call only returns ciphertext.
            destructive_hint=False,
            # Salted, so the same input yields a different vault string each time.
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def encrypt_secret(
        project: Annotated[
            str, Field(description="Project name, as returned by list_vault_projects.")
        ],
        secret: Annotated[str, Field(description="The plaintext to encrypt.")],
        variable_name: Annotated[
            str | None,
            Field(
                default=None,
                description="Ansible variable name; adds a ready to paste YAML block.",
            ),
        ] = None,
    ) -> EncryptOut:
        if not secret:
            raise ToolError("secret must not be empty")
        if len(secret) > max_secret_length:
            raise ToolError(f"secret exceeds the maximum of {max_secret_length} characters")

        vault = get_vault_service()
        try:
            vault_text = vault.encrypt(project, secret)
        except UnknownProjectError as exc:
            known = ", ".join(p.name for p in vault.projects)
            raise ToolError(f"{exc}. Configured projects: {known}") from exc

        yaml_snippet = None
        if variable_name:
            try:
                yaml_snippet = to_yaml_snippet(variable_name, vault_text)
            except InvalidVariableNameError as exc:
                raise ToolError(str(exc)) from exc

        configured = vault.get_project(project)
        return EncryptOut(
            project=configured.name,
            vault_id=configured.vault_id,
            vault_text=vault_text,
            yaml_snippet=yaml_snippet,
        )

    return server

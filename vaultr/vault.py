"""Encryption service built on Ansible's own vault implementation.

The PoC this replaces shelled out to ``ansible-vault`` with the user supplied
plaintext interpolated into a shell command, which allowed arbitrary command
execution. This module calls the library directly, so no shell is involved and no
plaintext is ever written to a file or an argument vector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ansible.parsing.vault import VaultLib, VaultSecret

from vaultr.config import ProjectConfig, VaultrConfig

# Ansible's own encrypt_string output indents the vault body by ten spaces.
YAML_INDENT = " " * 10

# Ansible variable names, used as the key of the generated YAML snippet. Restricting
# them keeps the snippet well formed and prevents injecting arbitrary YAML.
VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

# The vault ID Ansible uses when none is given. It produces a 1.1 header, which is
# understood by every Ansible release and carries no label.
DEFAULT_VAULT_ID = "default"


class VaultError(Exception):
    """Base class for encryption failures."""


class UnknownProjectError(VaultError):
    """Raised when a request names a project that is not configured."""


class InvalidVariableNameError(VaultError):
    """Raised when the requested YAML key is not a valid Ansible variable name."""


@dataclass(frozen=True, slots=True)
class Project:
    """Public view of a configured project. Deliberately carries no passphrase."""

    name: str
    description: str | None = None
    vault_id: str | None = None


def to_yaml_snippet(variable_name: str, vault_text: str) -> str:
    """Render a vault string as a ready to paste ``key: !vault |`` YAML block.

    Mirrors the output of ``ansible-vault encrypt_string --stdin-name``.

    Raises:
        InvalidVariableNameError: if ``variable_name`` is not a valid Ansible variable.
    """
    if not VARIABLE_NAME_RE.match(variable_name):
        raise InvalidVariableNameError(
            f"{variable_name!r} is not a valid Ansible variable name "
            "(letters, digits and underscore, not starting with a digit)"
        )
    body = "\n".join(f"{YAML_INDENT}{line}" for line in vault_text.splitlines())
    return f"{variable_name}: !vault |\n{body}"


class VaultService:
    """Encrypts plaintext with the passphrase belonging to a configured project.

    All passphrases are resolved once at construction, so a misconfigured project
    fails at startup rather than on the first request.
    """

    def __init__(self, projects: list[ProjectConfig]) -> None:
        self._projects: dict[str, Project] = {}
        self._vaults: dict[str, VaultLib] = {}

        for project in projects:
            vault_id = project.vault_id or DEFAULT_VAULT_ID
            passphrase = VaultSecret(project.resolve_passphrase().encode("utf-8"))
            self._vaults[project.name] = VaultLib(secrets=[(vault_id, passphrase)])
            self._projects[project.name] = Project(
                name=project.name,
                description=project.description,
                vault_id=project.vault_id,
            )

    @classmethod
    def from_config(cls, config: VaultrConfig) -> VaultService:
        return cls(config.projects)

    @property
    def projects(self) -> list[Project]:
        """Configured projects, in the order they appear in the config file."""
        return list(self._projects.values())

    def get_project(self, name: str) -> Project:
        """Look up a project by name.

        Raises:
            UnknownProjectError: if no such project is configured.
        """
        try:
            return self._projects[name]
        except KeyError:
            raise UnknownProjectError(f"unknown project {name!r}") from None

    def encrypt(self, project_name: str, plaintext: str) -> str:
        """Encrypt ``plaintext`` for ``project_name`` and return the vault string.

        Raises:
            UnknownProjectError: if no such project is configured.
        """
        project = self.get_project(project_name)
        vault = self._vaults[project.name]
        encrypted = vault.encrypt(
            plaintext.encode("utf-8"),
            vault_id=project.vault_id or DEFAULT_VAULT_ID,
        )
        return encrypted.decode("utf-8")

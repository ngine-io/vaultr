"""Encryption service built on Ansible's own vault implementation.

The PoC this replaces shelled out to ``ansible-vault`` with the user supplied
plaintext interpolated into a shell command, which allowed arbitrary command
execution. This module calls the library directly, so no shell is involved and no
plaintext is ever written to a file or an argument vector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ansible.errors import AnsibleError
from ansible.parsing.vault import VaultLib, VaultSecret, is_encrypted

from vaultr.config import ProjectConfig, VaultrConfig

# Ansible's own encrypt_string output indents the vault body by ten spaces.
YAML_INDENT = " " * 10

# Ansible variable names, used as the key of the generated YAML snippet. Restricting
# them keeps the snippet well formed and prevents injecting arbitrary YAML.
VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

# The vault ID Ansible uses when none is given. It produces a 1.1 header, which is
# understood by every Ansible release and carries no label.
DEFAULT_VAULT_ID = "default"

# Every vault string starts with this envelope header.
VAULT_HEADER = "$ANSIBLE_VAULT"


class VaultError(Exception):
    """Base class for encryption failures."""


class UnknownProjectError(VaultError):
    """Raised when a request names a project that is not configured."""


class InvalidVariableNameError(VaultError):
    """Raised when the requested YAML key is not a valid Ansible variable name."""


class NotVaultTextError(VaultError):
    """Raised when the input to re-encryption is not an Ansible Vault string."""


class DecryptionFailedError(VaultError):
    """Raised when a vault string does not belong to the named source project."""


class ReencryptNotAllowedError(VaultError):
    """Raised when the configuration forbids this source to target combination."""


@dataclass(frozen=True, slots=True)
class Project:
    """Public view of a configured project. Deliberately carries no passphrase."""

    name: str
    description: str | None = None
    vault_id: str | None = None
    reencrypt_targets: tuple[str, ...] | None = None
    """Projects this project's secrets may be re-encrypted into; None means any."""

    def may_reencrypt_to(self, target: str) -> bool:
        return self.reencrypt_targets is None or target in self.reencrypt_targets


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


def max_vault_text_length(max_secret_length: int) -> int:
    """Upper bound for accepted vault text, derived from the plaintext limit.

    A vault string is the plaintext hex encoded twice inside an envelope, so it settles
    at roughly 4.6x the plaintext once the YAML snippet indentation is included, on top
    of a fixed header of about 350 bytes. Bounding re-encryption input by the plaintext
    limit would reject a secret that was legitimately encrypted at exactly that size.
    """
    return max_secret_length * 6 + 1024


def normalise_vault_text(text: str) -> str:
    """Clean up a pasted vault string.

    Accepts what Vaultr itself hands out: the bare vault string, or the whole
    ``name: !vault |`` YAML block, whose ten space indentation Ansible rejects. Blank
    lines and per line indentation are removed so the envelope parses.

    Raises:
        NotVaultTextError: if the result is not an Ansible Vault string.
    """
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]

    # A pasted YAML snippet starts with the key line rather than the envelope.
    if lines and not lines[0].startswith(VAULT_HEADER) and "!vault" in lines[0]:
        lines = lines[1:]

    normalised = "\n".join(lines)
    if not normalised or not is_encrypted(normalised.encode("utf-8")):
        raise NotVaultTextError(
            "input is not an Ansible Vault string; it must start with $ANSIBLE_VAULT"
        )
    return normalised


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
                reencrypt_targets=(
                    None if project.reencrypt_targets is None else tuple(project.reencrypt_targets)
                ),
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
        return self._encrypt_bytes(self.get_project(project_name), plaintext.encode("utf-8"))

    def _encrypt_bytes(self, project: Project, plaintext: bytes) -> str:
        vault = self._vaults[project.name]
        encrypted = vault.encrypt(
            plaintext,
            vault_id=project.vault_id or DEFAULT_VAULT_ID,
        )
        return encrypted.decode("utf-8")

    def _decrypt_bytes(self, project: Project, vault_text: str) -> bytes:
        """Decrypt with one project's passphrase.

        Private on purpose: nothing outside this class may obtain plaintext, so the
        only caller is :meth:`reencrypt`, which immediately re-encrypts the result.
        """
        try:
            return self._vaults[project.name].decrypt(vault_text.encode("utf-8"))
        except AnsibleError as exc:
            # Ansible raises the same error type for a wrong passphrase and for
            # malformed input, and the caller already knows the envelope is valid.
            raise DecryptionFailedError(
                f"the vault string could not be decrypted with the passphrase of "
                f"project {project.name!r}"
            ) from exc

    def reencrypt(self, source_project: str, target_project: str, vault_text: str) -> str:
        """Move a secret from one project's passphrase to another's.

        The plaintext exists only between these two calls and is never returned.

        Raises:
            UnknownProjectError: if either project is not configured.
            NotVaultTextError: if the input is not an Ansible Vault string.
            ReencryptNotAllowedError: if the configuration forbids this combination.
            DecryptionFailedError: if the secret does not belong to the source project.
        """
        source = self.get_project(source_project)
        target = self.get_project(target_project)

        if not source.may_reencrypt_to(target.name):
            raise ReencryptNotAllowedError(
                f"re-encrypting from {source.name!r} to {target.name!r} is not allowed"
            )

        normalised = normalise_vault_text(vault_text)
        # Kept as bytes throughout, so a secret that is not valid UTF-8 survives.
        return self._encrypt_bytes(target, self._decrypt_bytes(source, normalised))

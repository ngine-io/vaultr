"""Project configuration: which projects exist and where their passphrase comes from."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, model_validator

# Project names end up in URLs and in the UI, vault IDs end up in the vault header
# where a ";" would corrupt the format.
ProjectName = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", strip_whitespace=True)
]
VaultId = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", strip_whitespace=True)
]


class ConfigError(Exception):
    """Raised when the configuration file is missing, malformed or incomplete."""


class ProjectConfig(BaseModel):
    """A single project and the passphrase its secrets are encrypted with.

    Exactly one passphrase source must be given. Prefer ``passphrase_env`` or
    ``passphrase_file`` in production so the passphrase never sits in the config file.
    """

    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    description: str | None = None
    vault_id: VaultId | None = None
    """Optional Ansible vault ID. Set it to emit a 1.2 header labelled with that ID."""

    passphrase: SecretStr | None = None
    passphrase_env: str | None = None
    passphrase_file: Path | None = None

    @model_validator(mode="after")
    def _exactly_one_passphrase_source(self) -> ProjectConfig:
        sources = [
            name
            for name, value in (
                ("passphrase", self.passphrase),
                ("passphrase_env", self.passphrase_env),
                ("passphrase_file", self.passphrase_file),
            )
            if value is not None
        ]
        if len(sources) != 1:
            given = ", ".join(sources) if sources else "none"
            raise ValueError(
                f"project {self.name!r} must define exactly one of "
                f"passphrase, passphrase_env or passphrase_file (got: {given})"
            )
        return self

    def resolve_passphrase(self) -> str:
        """Read the passphrase from its configured source.

        Raises:
            ConfigError: if the environment variable or file is missing or empty.
        """
        if self.passphrase is not None:
            passphrase = self.passphrase.get_secret_value()
            origin = "passphrase"
        elif self.passphrase_env is not None:
            value = os.environ.get(self.passphrase_env)
            if value is None:
                raise ConfigError(
                    f"project {self.name!r}: environment variable "
                    f"{self.passphrase_env!r} is not set"
                )
            passphrase, origin = value, f"passphrase_env {self.passphrase_env}"
        else:
            # The validator guarantees this is the remaining source.
            passphrase_file = self.passphrase_file
            try:
                passphrase = passphrase_file.read_text(encoding="utf-8")
            except OSError as exc:
                raise ConfigError(
                    f"project {self.name!r}: cannot read passphrase_file "
                    f"{passphrase_file}: {exc.strerror}"
                ) from exc
            origin = f"passphrase_file {passphrase_file}"

        # A passphrase read from a file almost always carries the editor's trailing
        # newline, which Ansible strips as well.
        passphrase = passphrase.strip("\r\n")
        if not passphrase:
            raise ConfigError(f"project {self.name!r}: passphrase from {origin} is empty")
        return passphrase


class VaultrConfig(BaseModel):
    """Root of the configuration file."""

    model_config = ConfigDict(extra="forbid")

    projects: list[ProjectConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_names(self) -> VaultrConfig:
        seen: set[str] = set()
        for project in self.projects:
            if project.name in seen:
                raise ValueError(f"duplicate project name {project.name!r}")
            seen.add(project.name)
        return self


def load_config(path: Path) -> VaultrConfig:
    """Load and validate the configuration file.

    Raises:
        ConfigError: on any missing file, YAML syntax error or schema violation.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc.strerror}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level")

    try:
        return VaultrConfig.model_validate(data)
    except ValueError as exc:
        raise ConfigError(f"invalid configuration in {path}: {exc}") from exc

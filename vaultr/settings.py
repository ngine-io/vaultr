"""Runtime settings, read from the environment and an optional .env file."""

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment settings. Every field maps to a ``VAULTR_``-prefixed variable."""

    model_config = SettingsConfigDict(
        env_prefix="VAULTR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Vaultr"
    """Title shown in the UI and the OpenAPI schema."""

    config_file: Path = Path("config.yml")
    """Path to the YAML file defining the projects and their vault passphrases."""

    root_path: str = ""
    """Mount prefix when served behind a reverse proxy on a sub path, e.g. ``/vaultr``."""

    log_level: str = "INFO"
    log_json: bool = False

    api_tokens: Annotated[list[str], NoDecode] = Field(default_factory=list)
    """Bearer tokens accepted by the API and the UI. Empty disables authentication."""

    max_secret_length: int = 65536
    """Upper bound on the plaintext size accepted per request, in characters."""

    docs_enabled: bool = True
    """Serve the interactive OpenAPI documentation at ``/api``."""

    mcp_enabled: bool = True
    """Serve the MCP endpoint at ``/mcp`` for agent clients."""

    @field_validator("api_tokens", mode="before")
    @classmethod
    def _split_tokens(cls, value: object) -> object:
        """Accept a comma separated list, which is what container runtimes hand over."""
        if isinstance(value, str):
            return [token.strip() for token in value.split(",") if token.strip()]
        return value

    @field_validator("root_path")
    @classmethod
    def _normalise_root_path(cls, value: str) -> str:
        return "/" + value.strip("/") if value.strip("/") else ""

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_tokens)

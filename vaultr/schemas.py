"""Request and response models for the JSON API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from vaultr.config import ProjectName


class ProjectOut(BaseModel):
    """A project a caller may encrypt for. Never carries the passphrase."""

    model_config = ConfigDict(json_schema_extra={"example": {"name": "prod-myproject"}})

    name: str
    description: str | None = None
    vault_id: str | None = None


class ProjectListOut(BaseModel):
    projects: list[ProjectOut]


class EncryptIn(BaseModel):
    """An encryption request."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "project": "prod-myproject",
                "secret": "s3cr3t",
                "variable_name": "db_password",
            }
        },
    )

    project: ProjectName = Field(description="Name of a configured project.")
    secret: str = Field(min_length=1, description="Plaintext to encrypt, encoded verbatim.")
    variable_name: str | None = Field(
        default=None,
        description="Ansible variable name. When given, a ready to paste YAML snippet "
        "is returned alongside the raw vault string.",
    )


class EncryptOut(BaseModel):
    """The encrypted result."""

    project: str
    vault_id: str | None = None
    vault_text: str = Field(description="The `$ANSIBLE_VAULT` string.")
    yaml_snippet: str | None = Field(
        default=None,
        description="`variable: !vault |` block, present when `variable_name` was given.",
    )


class HealthOut(BaseModel):
    status: str = "ok"
    version: str
    projects: int


class ErrorOut(BaseModel):
    detail: str

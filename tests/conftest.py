"""Shared fixtures: a small on-disk configuration and a client bound to it."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vaultr.app import create_app
from vaultr.settings import Settings

PROD_PASSPHRASE = "prod-passphrase"
TEST_PASSPHRASE = "test-passphrase"

CONFIG_YAML = """
projects:
  - name: prod-myproject
    description: Production
    passphrase: {prod}
  - name: test-myproject
    description: Staging
    passphrase: {test}
  - name: labelled
    vault_id: labelled
    passphrase: {test}
  - name: restricted
    description: May only be re-encrypted into test-myproject
    passphrase: {prod}
    reencrypt_targets:
      - test-myproject
  - name: sealed
    description: May not be re-encrypted anywhere
    passphrase: {prod}
    reencrypt_targets: []
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.yml"
    path.write_text(CONFIG_YAML.format(prod=PROD_PASSPHRASE, test=TEST_PASSPHRASE))
    return path


@pytest.fixture
def settings(config_file: Path) -> Settings:
    return Settings(config_file=config_file, api_tokens=[], _env_file=None)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth_client(config_file: Path) -> Iterator[TestClient]:
    """A client for an instance that requires a bearer token."""
    secured = Settings(config_file=config_file, api_tokens=["s3cr3t-token"], _env_file=None)
    with TestClient(create_app(secured)) as test_client:
        yield test_client

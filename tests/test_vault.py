"""Encryption behaviour, verified against Ansible's own decryption."""

from __future__ import annotations

import pytest
import yaml
from ansible.parsing.vault import VaultLib, VaultSecret

from vaultr.config import ProjectConfig, VaultrConfig, load_config
from vaultr.vault import (
    InvalidVariableNameError,
    UnknownProjectError,
    VaultService,
    to_yaml_snippet,
)

from .conftest import PROD_PASSPHRASE, TEST_PASSPHRASE


def decrypt(vault_text: str, passphrase: str) -> str:
    """Decrypt with a plain Ansible VaultLib, as a real Ansible run would."""
    lib = VaultLib(secrets=[("default", VaultSecret(passphrase.encode()))])
    return lib.decrypt(vault_text.encode()).decode()


@pytest.fixture
def service(config_file) -> VaultService:
    return VaultService.from_config(load_config(config_file))


def test_projects_preserve_config_order(service: VaultService) -> None:
    assert [p.name for p in service.projects] == [
        "prod-myproject",
        "test-myproject",
        "labelled",
    ]


def test_projects_never_expose_the_passphrase(service: VaultService) -> None:
    rendered = repr(service.projects)
    assert PROD_PASSPHRASE not in rendered
    assert TEST_PASSPHRASE not in rendered


def test_encrypts_with_the_project_passphrase(service: VaultService) -> None:
    vault_text = service.encrypt("prod-myproject", "hunter2")
    assert vault_text.startswith("$ANSIBLE_VAULT;1.1;AES256")
    assert decrypt(vault_text, PROD_PASSPHRASE) == "hunter2"


def test_each_project_uses_its_own_passphrase(service: VaultService) -> None:
    vault_text = service.encrypt("test-myproject", "hunter2")
    assert decrypt(vault_text, TEST_PASSPHRASE) == "hunter2"
    with pytest.raises(Exception):  # noqa: B017 - Ansible raises its own error type
        decrypt(vault_text, PROD_PASSPHRASE)


def test_vault_id_produces_a_labelled_1_2_header(service: VaultService) -> None:
    vault_text = service.encrypt("labelled", "hunter2")
    assert vault_text.startswith("$ANSIBLE_VAULT;1.2;AES256;labelled")


def test_encryption_is_salted(service: VaultService) -> None:
    # Two runs must not produce the same ciphertext, or equal secrets would be
    # recognisable from their vault strings alone.
    first = service.encrypt("prod-myproject", "hunter2")
    second = service.encrypt("prod-myproject", "hunter2")
    assert first != second


@pytest.mark.parametrize(
    "plaintext",
    ["hunter2", "multi\nline\nsecret", "unicode: äöü 🔐", "  leading and trailing  ", "x" * 10000],
    ids=["simple", "multiline", "unicode", "whitespace", "large"],
)
def test_round_trip_is_byte_exact(service: VaultService, plaintext: str) -> None:
    assert decrypt(service.encrypt("prod-myproject", plaintext), PROD_PASSPHRASE) == plaintext


def test_shell_metacharacters_are_data_not_code(service: VaultService) -> None:
    # The PoC interpolated the plaintext into a shell command. Nothing here shells out,
    # so this survives the round trip unchanged instead of executing.
    payload = "'; touch /tmp/pwned; echo '"
    assert decrypt(service.encrypt("prod-myproject", payload), PROD_PASSPHRASE) == payload


def test_unknown_project_is_rejected(service: VaultService) -> None:
    with pytest.raises(UnknownProjectError, match="unknown project"):
        service.encrypt("nope", "hunter2")


def test_get_project_returns_public_metadata_only(service: VaultService) -> None:
    project = service.get_project("labelled")
    assert project.vault_id == "labelled"
    assert not hasattr(project, "passphrase")


def test_yaml_snippet_matches_ansible_layout(service: VaultService) -> None:
    vault_text = service.encrypt("prod-myproject", "hunter2")
    snippet = to_yaml_snippet("db_password", vault_text)

    lines = snippet.splitlines()
    assert lines[0] == "db_password: !vault |"
    # ansible-vault encrypt_string indents the body by exactly ten spaces.
    assert all(line.startswith(" " * 10) and line[10] != " " for line in lines[1:])


def test_yaml_snippet_parses_back_to_the_vault_text(service: VaultService) -> None:
    vault_text = service.encrypt("prod-myproject", "hunter2")
    snippet = to_yaml_snippet("db_password", vault_text)

    loader = yaml.SafeLoader
    loader.add_constructor("!vault", lambda l, n: l.construct_scalar(n))  # noqa: E741
    parsed = yaml.load(snippet, Loader=loader)  # noqa: S506 - constructor is restricted

    assert decrypt(parsed["db_password"], PROD_PASSPHRASE) == "hunter2"


@pytest.mark.parametrize(
    "name",
    ["1leading_digit", "with-dash", "with space", "", "a: b", "x\ny: !!python/object"],
)
def test_invalid_variable_names_are_rejected(service: VaultService, name: str) -> None:
    vault_text = service.encrypt("prod-myproject", "hunter2")
    with pytest.raises(InvalidVariableNameError):
        to_yaml_snippet(name, vault_text)


def test_missing_passphrase_fails_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    from vaultr.config import ConfigError

    monkeypatch.delenv("VAULTR_ABSENT", raising=False)
    config = VaultrConfig(projects=[ProjectConfig(name="a", passphrase_env="VAULTR_ABSENT")])
    with pytest.raises(ConfigError):
        VaultService.from_config(config)

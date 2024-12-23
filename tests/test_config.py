"""Configuration loading and passphrase resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultr.config import ConfigError, ProjectConfig, load_config


def write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yml"
    path.write_text(content)
    return path


def test_loads_projects(config_file: Path) -> None:
    config = load_config(config_file)
    assert [p.name for p in config.projects] == ["prod-myproject", "test-myproject", "labelled"]
    assert config.projects[0].description == "Production"
    assert config.projects[2].vault_id == "labelled"


def test_missing_file_reports_path(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read config file"):
        load_config(tmp_path / "absent.yml")


def test_invalid_yaml(tmp_path: Path) -> None:
    path = write(tmp_path, "projects: [oops\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(path)


def test_top_level_must_be_a_mapping(tmp_path: Path) -> None:
    path = write(tmp_path, "- just\n- a list\n")
    with pytest.raises(ConfigError, match="must contain a YAML mapping"):
        load_config(path)


def test_rejects_empty_project_list(tmp_path: Path) -> None:
    path = write(tmp_path, "projects: []\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_rejects_duplicate_names(tmp_path: Path) -> None:
    path = write(
        tmp_path, "projects:\n  - name: dup\n    passphrase: a\n  - name: dup\n    passphrase: b\n"
    )
    with pytest.raises(ConfigError, match="duplicate project name"):
        load_config(path)


def test_rejects_unknown_keys(tmp_path: Path) -> None:
    path = write(tmp_path, "projects:\n  - name: a\n    passphrase: x\n    typo: y\n")
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize(
    "body",
    [
        "projects:\n  - name: a\n",
        "projects:\n  - name: a\n    passphrase: x\n    passphrase_env: Y\n",
    ],
    ids=["no source", "two sources"],
)
def test_requires_exactly_one_passphrase_source(tmp_path: Path, body: str) -> None:
    with pytest.raises(ConfigError, match="exactly one of"):
        load_config(write(tmp_path, body))


def test_rejects_project_name_that_would_break_urls(tmp_path: Path) -> None:
    path = write(tmp_path, "projects:\n  - name: 'bad name/../x'\n    passphrase: x\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_rejects_vault_id_that_would_break_the_header(tmp_path: Path) -> None:
    # A ";" in the vault ID would corrupt the "$ANSIBLE_VAULT;1.2;AES256;<id>" header.
    path = write(tmp_path, "projects:\n  - name: a\n    vault_id: 'x;y'\n    passphrase: x\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_inline_passphrase_resolves() -> None:
    assert ProjectConfig(name="a", passphrase="hunter2").resolve_passphrase() == "hunter2"


def test_passphrase_env_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAULTR_TEST_PASSPHRASE", "from-env")
    assert (
        ProjectConfig(name="a", passphrase_env="VAULTR_TEST_PASSPHRASE").resolve_passphrase()
        == "from-env"
    )


def test_passphrase_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAULTR_ABSENT", raising=False)
    with pytest.raises(ConfigError, match="is not set"):
        ProjectConfig(name="a", passphrase_env="VAULTR_ABSENT").resolve_passphrase()


def test_passphrase_file_resolves_and_strips_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "pw"
    path.write_text("from-file\n")
    assert ProjectConfig(name="a", passphrase_file=path).resolve_passphrase() == "from-file"


def test_passphrase_file_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read passphrase_file"):
        ProjectConfig(name="a", passphrase_file=tmp_path / "absent").resolve_passphrase()


def test_empty_passphrase_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "pw"
    path.write_text("\n")
    with pytest.raises(ConfigError, match="is empty"):
        ProjectConfig(name="a", passphrase_file=path).resolve_passphrase()


def test_inline_passphrase_is_not_leaked_by_repr() -> None:
    assert "hunter2" not in repr(ProjectConfig(name="a", passphrase="hunter2"))

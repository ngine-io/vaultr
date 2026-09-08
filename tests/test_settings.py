"""Settings parsing."""

from __future__ import annotations

import pytest

from vaultr.settings import Settings


def make(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_defaults() -> None:
    settings = make()
    assert settings.app_name == "Vaultr"
    assert settings.api_tokens == []
    assert settings.auth_enabled is False


def test_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAULTR_APP_NAME", "Custom")
    monkeypatch.setenv("VAULTR_LOG_LEVEL", "DEBUG")
    settings = make()
    assert settings.app_name == "Custom"
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a,b", ["a", "b"]),
        (" a , b ", ["a", "b"]),
        ("single", ["single"]),
        ("", []),
        (",,", []),
    ],
)
def test_api_tokens_accept_a_comma_separated_list(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("VAULTR_API_TOKENS", raw)
    assert make().api_tokens == expected


def test_auth_enabled_follows_the_tokens() -> None:
    assert make(api_tokens=["t"]).auth_enabled is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", ""), ("/", ""), ("vaultr", "/vaultr"), ("/vaultr/", "/vaultr")],
)
def test_root_path_is_normalised(raw: str, expected: str) -> None:
    assert make(root_path=raw).root_path == expected


def test_reencrypt_is_enabled_by_default() -> None:
    assert make().reencrypt_enabled is True


def test_reencrypt_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAULTR_REENCRYPT_ENABLED", "false")
    assert make().reencrypt_enabled is False

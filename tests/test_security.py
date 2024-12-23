"""Token comparison."""

from __future__ import annotations

import pytest

from vaultr.security import token_is_valid


@pytest.mark.parametrize(
    ("token", "allowed", "expected"),
    [
        ("a", ["a"], True),
        ("a", ["b", "a"], True),
        ("a", ["b"], False),
        ("a", [], False),
        ("", [""], True),
        ("a", ["A"], False),
        ("a ", ["a"], False),
    ],
)
def test_token_is_valid(token: str, allowed: list[str], expected: bool) -> None:
    assert token_is_valid(token, allowed) is expected

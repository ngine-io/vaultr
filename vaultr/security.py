"""Bearer token authentication for the API and the UI."""

from __future__ import annotations

from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False, description="Static bearer token")

Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def token_is_valid(token: str, allowed: list[str]) -> bool:
    """Compare ``token`` against every allowed token in constant time."""
    # Every candidate is compared so the runtime does not reveal which one matched,
    # and `any` over a list comprehension avoids short circuiting on the first hit.
    return any([compare_digest(token, candidate) for candidate in allowed])  # noqa: C419


async def require_token(request: Request, credentials: Credentials) -> None:
    """FastAPI dependency enforcing a bearer token when any token is configured.

    With no tokens configured, authentication is disabled and every request passes.

    Raises:
        HTTPException: 401 when the token is missing or does not match.
    """
    allowed: list[str] = request.app.state.settings.api_tokens
    if not allowed:
        return

    if credentials is None or not token_is_valid(credentials.credentials, allowed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

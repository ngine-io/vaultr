"""Liveness and readiness probes. Deliberately unauthenticated."""

from __future__ import annotations

from fastapi import APIRouter

from vaultr.dependencies import VaultServiceDep
from vaultr.schemas import HealthOut
from vaultr.version import __version__

router = APIRouter(tags=["health"], include_in_schema=False)


@router.get("/healthz", response_model=HealthOut, summary="Liveness probe")
async def healthz(vault: VaultServiceDep) -> HealthOut:
    return HealthOut(status="ok", version=__version__, projects=len(vault.projects))


@router.get("/readyz", response_model=HealthOut, summary="Readiness probe")
async def readyz(vault: VaultServiceDep) -> HealthOut:
    """Ready once the configuration is loaded and every passphrase has resolved."""
    return HealthOut(status="ready", version=__version__, projects=len(vault.projects))

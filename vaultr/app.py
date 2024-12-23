"""Application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger

from vaultr.config import ConfigError, load_config
from vaultr.logging import configure_logging
from vaultr.routes import api, health, web
from vaultr.settings import Settings
from vaultr.vault import VaultService
from vaultr.version import __version__

STATIC_DIR = Path(__file__).resolve().parent / "static"

DESCRIPTION = """
Encrypt a secret into an [Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/)
string without ever handling the vault passphrase yourself.

Projects and their passphrases are defined server side. Pick a project, submit a
secret, and receive the encrypted string. Decryption is intentionally not offered.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the configuration and resolve every passphrase before serving traffic."""
    settings: Settings = app.state.settings

    config = load_config(settings.config_file)
    app.state.vault_service = VaultService.from_config(config)

    logger.info(
        "{} {} ready with {} project(s) from {}",
        settings.app_name,
        __version__,
        len(config.projects),
        settings.config_file,
    )
    if not settings.auth_enabled:
        logger.warning(
            "No VAULTR_API_TOKENS configured: anyone who can reach this service can "
            "encrypt with any project passphrase. Put it behind an authenticating proxy."
        )

    yield

    logger.info("Shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    Raises:
        ConfigError: at startup if the configuration is missing or invalid.
    """
    settings = settings or Settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        root_path=settings.root_path,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:  # pragma: no cover - only hit when the asset build has not run
        logger.warning("Static directory {} is missing, the UI will be unstyled", STATIC_DIR)

    app.include_router(health.router)
    app.include_router(api.router)
    app.include_router(web.router)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Everything is served from this origin; no third party script may run on a
        # page that handles plaintext secrets.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; "
            "base-uri 'none'",
        )
        return response

    return app


def main() -> None:
    """Console script entry point: serve the application with uvicorn."""
    import uvicorn

    settings = Settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    try:
        uvicorn.run(
            "vaultr.app:app",
            host="0.0.0.0",  # noqa: S104 - containers must bind all interfaces
            port=8000,
            log_config=None,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
    except ConfigError as exc:
        logger.error("Configuration error: {}", exc)
        raise SystemExit(1) from exc


app = create_app()

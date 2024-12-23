"""Application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from vaultr.config import ConfigError, load_config
from vaultr.logging import configure_logging
from vaultr.mcp_server import build_mcp_server
from vaultr.metadata import API_DOCS_PATH, MCP_PATH
from vaultr.routes import api, health, web
from vaultr.security import token_is_valid
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

    # The mounted MCP app needs its session manager running for the lifetime of the
    # application; mounted sub-apps do not get their own lifespan.
    mcp_server = getattr(app.state, "mcp_server", None)
    if mcp_server is None:
        yield
    else:
        async with mcp_server.session_manager.run():
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
        docs_url=API_DOCS_PATH if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url=f"{API_DOCS_PATH}/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings

    # `make assets` generates this directory, so it is absent in a fresh checkout and
    # in a CI run that only installs Python. Create it before mounting: the route then
    # always exists, so url_for("static") resolves and the templates render unstyled
    # instead of failing outright, and a missing asset is a clean 404 rather than the
    # RuntimeError StaticFiles raises for a directory that is not there.
    try:
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover - read-only installation
        pass
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR), check_dir=False),
        name="static",
    )
    if not (STATIC_DIR / "css" / "main.css").is_file():
        logger.warning("Stylesheet is missing, the UI will be unstyled. Run `make assets`.")

    app.include_router(health.router)
    app.include_router(api.router)
    app.include_router(web.router)

    app.state.mcp_server = None
    if settings.mcp_enabled:
        mcp_server = build_mcp_server(
            lambda: app.state.vault_service,
            max_secret_length=settings.max_secret_length,
            app_name=settings.app_name,
        )
        # The sub-app serves the endpoint at its root so the mount point supplies the
        # /mcp prefix rather than doubling it.
        app.mount(MCP_PATH, mcp_server.streamable_http_app(streamable_http_path="/"))
        app.state.mcp_server = mcp_server

    @app.middleware("http")
    async def mcp_authentication(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Apply the bearer token to the mounted MCP app.

        Route dependencies do not reach a mounted sub-app, so the check lives in
        middleware rather than in the MCP server itself.
        """
        allowed: list[str] = request.app.state.settings.api_tokens
        if allowed and request.url.path.rstrip("/").startswith(MCP_PATH):
            header = request.headers.get("Authorization", "")
            scheme, _, token = header.partition(" ")
            if scheme.lower() != "bearer" or not token_is_valid(token, allowed):
                return JSONResponse(
                    {"detail": "Missing or invalid bearer token"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

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

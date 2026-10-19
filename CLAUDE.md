# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Vaultr encrypts secrets into Ansible Vault strings through a web UI, a JSON API and an MCP endpoint, using passphrases held server side. It also re-encrypts a vault string from one project's passphrase to another's. There is deliberately no decryption endpoint, and no interface may ever return plaintext.

## Commands

`make` with no target lists every target. The ones used most:

```bash
make install        # uv sync --group dev --group docs && npm ci
make assets         # copy Tabler CSS, htmx and assets/* into vaultr/static/ (generated, untracked)
make dev            # uvicorn with --reload and debug logging
make lint           # ruff check + ruff format --check (what the Lint workflow runs)
make format         # ruff --fix + ruff format
make test           # pytest with coverage on the current interpreter
make test-all       # pytest on every version in PYTHON_VERSIONS, each in .venvs/<ver>
make docs-build     # mkdocs build --strict, as CI does
make image          # build the container image with docker, or podman if docker is missing
```

Run a single test: `uv run --group dev pytest tests/test_vault.py::test_name -q`. Run the suite on one specific interpreter: `uv run --isolated --python 3.15 --group dev pytest -q`.

pytest uses `--strict-markers --strict-config`, and `filterwarnings = error`. Any new warning fails the suite, except a `DeprecationWarning`.

## Architecture

**One service, three front ends.** `VaultService` in `vaultr/vault.py` is the security-critical core. It calls `ansible.parsing.vault.VaultLib` directly; never shell out to `ansible-vault`, which is how the original PoC allowed command injection. The JSON API (`routes/api.py`), the htmx UI (`routes/web.py`) and the MCP tools (`mcp_server.py`) are thin adapters over it. Each one maps the `VaultError` subclasses to its own error shape: HTTP 404/403/422/413 for the API, a rendered error for the UI, `ToolError` for MCP. A new operation or error type has to be wired into all three, and each has its own test module.

**Decryption stays private.** `VaultService._decrypt_bytes` exists only so `reencrypt` can re-encrypt the result straight away. Plaintext stays as bytes the whole way, so a secret that isn't valid UTF-8 survives.

**Startup does the validation.** `create_app()` in `vaultr/app.py` builds the app, and the module-level `app = create_app()` is what uvicorn serves. The `lifespan` hook loads `config.yml` (`vaultr/config.py`) and resolves every project passphrase from `passphrase`, `passphrase_env` or `passphrase_file`. So a misconfigured project fails at boot, not on the first request. The hook stores the service on `app.state.vault_service`, and routes reach it through `dependencies.py`.

**Two layers of config:**
- `Settings` (`vaultr/settings.py`): deployment settings from `VAULTR_*` env vars or `.env`. Covers tokens, size limits, and feature toggles for docs, MCP and re-encryption.
- `config.yml`: the projects and their `reencrypt_targets` allowlists. Leaving `reencrypt_targets` unset means any target is allowed; `[]` means none.

**Auth:** an empty `VAULTR_API_TOKENS` disables auth, and the app logs a warning. API and web routes enforce the bearer token through the `require_token` dependency. Route dependencies don't reach mounted sub-apps, so the MCP mount at `/mcp` is guarded by HTTP middleware in `app.py` instead. Its session manager also runs inside the main app's lifespan, for the same reason.

**Size limits:** `max_secret_length` caps plaintext. Vault text accepted for re-encryption is capped by the derived `max_vault_text_length()`, because a vault string is about 4.6x the size of its plaintext.

**Frontend:** Jinja2 templates in `vaultr/templates/` (the partials and inline SVG icons are in subdirectories), with Tabler CSS and htmx. Nothing is compiled; `make assets` only copies files. The Content Security Policy only allows content from the app's own origin (`'self'`), so never add CDN assets or inline scripts. Without `make assets` the app still starts but the UI is unstyled. The package-data globs in `pyproject.toml` must stay recursive (`**`), or the partials are dropped from the wheel.

## Tests

Fixtures in `tests/conftest.py` write a temporary `config.yml` with five projects that cover labelled vault IDs and restricted or sealed re-encryption targets. They provide `client` (auth disabled) and `auth_client` (token `s3cr3t-token`). Encryption tests decrypt the output with a plain `VaultLib` instead of comparing against fixed ciphertext, because ciphertext is salted and differs on every run.

## CI and container

- The Lint, Python tests, Frontend assets and Docs workflows run on every push and pull request.
- `container.yml` runs only on pushes to `main` and `v*` tags. It builds the image and smoke-tests it: HTTP checks, a round trip through real Ansible, and a real MCP client. A container regression therefore only shows up after merge. Pushes to `main` also publish the docs to GitHub Pages.
- The runtime image runs as UID 1000 with group 0 and no passwd entry, so it works when the runtime assigns an arbitrary UID (OpenShift). It sets `HOME`, `ANSIBLE_HOME`, `USER` and `LOGNAME` because ansible-core needs them at import time; `getpass.getuser()` crashes without them.
- Rootless podman injects a passwd entry for the container user, which hides that class of bug. To reproduce what CI sees, run with `podman run --passwd=false --user 4321:0 ...`.
- The Dockerfile uses a named `base` stage rather than an `ARG` for the Python image, so Dependabot can keep updating it.

## Python version support

Supported versions are listed in several places that must stay in sync:
- `requires-python` and the classifiers in `pyproject.toml`
- ruff's `target-version`
- the matrix in `.github/workflows/tests.yml`
- `PYTHON_VERSIONS` in the Makefile
- the version badge in the README

ansible-core sets the real upper bound: the 2.21.x releases fail on import under Python 3.15, which needs 2.22. Until 2.22 is locked, 3.15 is held back everywhere: the `matrix` job in `tests.yml` adds it automatically once `uv.lock` carries ansible-core 2.22 or newer, and the classifier, README badge and `PYTHON_VERSIONS` should be updated in the same PR.

## Releasing

The version lives in `vaultr/version.py`. Pushing a `vX.Y.Z` tag builds and pushes `ghcr.io/ngine-io/vaultr:X.Y.Z` and `:X.Y`. `make release` publishes the package to PyPI.

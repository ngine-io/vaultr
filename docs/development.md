# Development

## Setup

```bash
git clone https://github.com/ngine-io/vaultr.git
cd vaultr
make install
```

`make install` runs `uv sync` for Python and `npm ci` for the frontend toolchain.

## Common tasks

`make` on its own lists every target:

| Target             | Purpose                                                |
| ------------------ | ------------------------------------------------------ |
| `make dev`         | Serve with auto reload and debug logging.               |
| `make assets`      | Collect the Tabler stylesheet and vendored scripts.     |
| `make test`        | Run the tests with coverage.                            |
| `make test-all`    | Run the tests on every supported Python version.        |
| `make lint`        | Ruff lint and format check.                             |
| `make format`      | Apply autofixes and format.                             |
| `make check`       | Everything CI runs.                                     |
| `make docs`        | Serve this documentation locally.                       |
| `make docs-build`  | Build the documentation as CI does, with `--strict`.    |
| `make image`       | Build the container image.                              |

## Layout

```
vaultr/
├── app.py            # application factory, middleware, lifespan
├── config.py         # config.yml schema and passphrase resolution
├── vault.py          # encrypt / re-encrypt service, the security critical core
├── mcp_server.py     # MCP tools, mounted at /mcp
├── settings.py       # environment driven settings
├── security.py       # bearer token authentication
├── dependencies.py   # shared FastAPI dependencies
├── schemas.py        # API request and response models
├── routes/           # api, web and health routers
├── templates/        # Jinja2 templates
└── static/           # generated: built by `make assets`
assets/               # source: custom.css and app.js
tests/
docs/
```

`vaultr/static/` is generated and not in version control. Run `make assets` after a
fresh clone, or the UI comes up unstyled.

## Frontend

The UI is built with [Tabler](https://tabler.io), a Bootstrap 5 component framework.
Tabler ships compiled CSS, so there is no build step: `make assets` copies
`tabler.min.css`, Tabler's theme script and htmx out of `node_modules` into
`vaultr/static/`, alongside `assets/custom.css` and `assets/app.js`.

Because nothing compiles, there is no class scanning and no purge: every Tabler class
is available in the templates without registering it anywhere.

### Theme switching

Tabler themes on a `data-bs-theme` attribute on `<html>` and ships
`tabler-theme.min.js` to manage it. That script reads the `tabler-theme` localStorage
key, falls back to the system preference, and also honours a `?theme=` query
parameter. It is loaded **synchronously right after `<body>`**, which is what Tabler
requires; deferring it makes the page flash the light theme before switching.

The navbar shows one of two icons, using Tabler's `hide-theme-dark` and
`hide-theme-light` helpers so only the switch for the inactive theme is visible. The
links carry `?theme=` so they still work if `app.js` fails to load; `app.js`
intercepts the click, sets the attribute and stores the choice, which avoids a
navigation and keeps an encryption result on screen.

Icons are Tabler outline SVGs inlined as Jinja partials under
`vaultr/templates/partials/icons/`. Nothing is fetched from a CDN, which the Content
Security Policy also enforces.

## Tests

```bash
make test
```

The suite covers configuration parsing, encryption, both route layers, settings and
token comparison. Encryption tests decrypt their output with a plain Ansible
`VaultLib` rather than asserting on fixed ciphertext, so they verify real
compatibility instead of an implementation detail.

## Releasing

Version lives in `vaultr/version.py`.

1. Bump it and update the changelog.
2. Tag the commit `vX.Y.Z` and push the tag.
3. CI builds and pushes `ghcr.io/ngine-io/vaultr:X.Y.Z` and `:X.Y`.
4. `make release` publishes to PyPI.

## Documentation

`make docs` serves this site locally on port 8001. Pull requests build it with
`--strict`, so a broken link or an unknown setting fails the check before merge.

Pushing to `main` publishes it to <https://ngine-io.github.io/vaultr/> through the
`Docs` workflow, which uploads the built site as a Pages artifact and deploys it with
GitHub's own Pages actions. There is no `gh-pages` branch, and no local publish step:
merging is what publishes.

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
| `make assets`      | Compile the stylesheet and vendor htmx.                 |
| `make assets-watch`| Recompile the stylesheet as templates change.           |
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
├── vault.py          # encryption service, the security critical core
├── settings.py       # environment driven settings
├── security.py       # bearer token authentication
├── dependencies.py   # shared FastAPI dependencies
├── schemas.py        # API request and response models
├── routes/           # api, web and health routers
├── templates/        # Jinja2 templates
└── static/           # generated: built by `make assets`
assets/               # source: Tailwind entrypoint and app.js
tests/
docs/
```

`vaultr/static/` is generated and not in version control. Run `make assets` after a
fresh clone, or the UI comes up unstyled.

## Frontend

The stylesheet is Tailwind CSS v4 with the daisyUI plugin, compiled from
`assets/main.css`. Tailwind scans `vaultr/templates/` for utility classes, declared
through `@source` in that file, so a class only used in Python code will not survive
the build.

Interactivity is htmx plus a small `assets/app.js` for the copy buttons. Both are
served from `/static`; nothing is loaded from a CDN, which the Content Security Policy
also enforces.

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

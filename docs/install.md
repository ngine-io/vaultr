# Install

## Container

The published image is the recommended way to run Vaultr.

```bash
docker run --rm -p 8000:8000 \
  -v ./config.yml:/app/config.yml:ro \
  -e VAULTR_PASSPHRASE_PROD=... \
  -e VAULTR_PASSPHRASE_TEST=... \
  ghcr.io/ngine-io/vaultr:main
```

Images are published to `ghcr.io/ngine-io/vaultr` for `linux/amd64` and `linux/arm64`.
Tags follow the repository: `main` for the branch, plus `X.Y.Z` and `X.Y` for releases.

The image ships a placeholder `/app/config.yml`, so mount your own over it.

### Compose

```yaml
services:
  vaultr:
    image: ghcr.io/ngine-io/vaultr:main
    ports:
      - "8000:8000"
    environment:
      VAULTR_API_TOKENS: ${VAULTR_API_TOKENS}
    volumes:
      - ./config.yml:/app/config.yml:ro
      - ./secrets:/run/secrets:ro
```

## From source

Vaultr uses [uv](https://docs.astral.sh/uv/) for Python and npm for the frontend
assets. Both are needed, because the UI stylesheet and scripts come from the
[Tabler](https://tabler.io) npm package.

```bash
git clone https://github.com/ngine-io/vaultr.git
cd vaultr

uv sync                  # Python dependencies
npm ci && npm run build  # compile static/css/main.css and vendor htmx

cp .env.example .env     # then set your project passphrases
uv run vaultr-ngine
```

The service listens on port 8000.

!!! tip "Running without the asset build"
    The application still starts if the assets were never built; the UI is simply
    unstyled and the JSON API is unaffected.

## Behind a reverse proxy

Set `VAULTR_ROOT_PATH` when Vaultr is served from a sub path, so generated links and
form actions keep the prefix:

```bash
VAULTR_ROOT_PATH=/vaultr
```

Vaultr trusts `X-Forwarded-*` headers, so terminate TLS at the proxy and make sure the
proxy sets them.

## Health checks

| Endpoint   | Purpose                                                       |
| ---------- | ------------------------------------------------------------- |
| `/healthz` | Liveness. The process is up.                                   |
| `/readyz`  | Readiness. Config loaded and every passphrase resolved.        |

Both are unauthenticated so that probes work without a token.

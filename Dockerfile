# Single source of truth for the interpreter. Both Python stages derive from it, so
# the venv built below can never be copied onto a different Python or glibc.
# A named stage is used instead of an ARG because Dependabot does not resolve
# ARG substitution in FROM and would stop updating the base image.
FROM docker.io/python:3.14.7-slim AS base

# Asset stage: collect Tabler's prebuilt stylesheet and the vendored scripts.
# Tabler ships compiled CSS, so nothing is compiled here and the templates are not
# needed; npm only resolves and copies files.
FROM docker.io/node:22-slim AS assets

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY assets ./assets
RUN npm run build

# Build stage: install the locked dependency set into a self-contained venv.
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/vaultr

WORKDIR /build
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY vaultr ./vaultr
# The built assets are packaged into the wheel, so they must land before the sync.
COPY --from=assets /build/vaultr/static ./vaultr/static
RUN uv sync --locked --no-dev --no-editable

# Runtime stage: only the venv, no uv, no Node and no build context.
FROM base

# Importing ansible.parsing.vault loads Ansible's constants, which insist on a
# writable Ansible home. Without HOME set it falls back to the working directory,
# which the unprivileged user cannot write to. Group 0 with g+rwX keeps this working
# under runtimes that assign an arbitrary UID, such as OpenShift.
ENV PATH="/opt/vaultr/bin:$PATH" \
    HOME=/home/vaultr \
    ANSIBLE_HOME=/home/vaultr/.ansible \
    VAULTR_CONFIG_FILE=/app/config.yml

COPY --from=builder /opt/vaultr /opt/vaultr

RUN mkdir -p /home/vaultr/.ansible /app \
    && chown -R 1000:0 /home/vaultr /app \
    && chmod -R g+rwX /home/vaultr

WORKDIR /app
COPY ./docker/config.yml .

EXPOSE 8000/tcp
USER 1000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()"]

ENTRYPOINT ["vaultr-ngine"]

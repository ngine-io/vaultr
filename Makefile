PYTHON_VERSIONS ?= 3.11 3.12 3.13 3.14
IMAGE ?= ghcr.io/ngine-io/vaultr
PORT ?= 8000

# Prefer docker, fall back to podman.
CONTAINER_ENGINE ?= $(shell command -v docker 2>/dev/null || command -v podman 2>/dev/null)

.DEFAULT_GOAL := help

.PHONY: help install assets run dev lint format check test test-all \
        cov clean build lock upgrade docs docs-build image image-run \
        test-release release

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} \
		/^##@ / {printf "\n\033[1m%s\033[0m\n", substr($$0, 5); next} \
		/^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' \
		$(MAKEFILE_LIST)
	@printf "\nOverridable: PORT=%s IMAGE=%s\n" "$(PORT)" "$(IMAGE)"

##@ Setup

install: ## Install Python and frontend dependencies
	uv sync --group dev --group docs
	npm ci

assets: ## Collect the Tabler stylesheet and vendored scripts
	npm run build

##@ Run

run: assets ## Serve the app on localhost (override with PORT=)
	VAULTR_PASSPHRASE_PROD=foobar VAULTR_PASSPHRASE_TEST=barfoo uv run uvicorn vaultr.app:app --host 0.0.0.0 --port $(PORT)

dev: assets ## Serve with auto reload and debug logging
	VAULTR_LOG_LEVEL=DEBUG uv run uvicorn vaultr.app:app --reload --port $(PORT)

##@ Quality

lint: ## Check formatting and lint rules
	uv run --only-group dev ruff check .
	uv run --only-group dev ruff format --check .

format: ## Apply autofixes and format the code
	uv run --only-group dev ruff check --fix .
	uv run --only-group dev ruff format .

test: ## Run the tests on the current interpreter
	uv run --group dev pytest --cov --cov-report=term-missing

test-all: ## Run the tests on every supported interpreter
	@for v in $(PYTHON_VERSIONS); do \
		echo "===== Python $$v ====="; \
		UV_PROJECT_ENVIRONMENT=.venvs/$$v uv run --locked --python $$v --group dev pytest -q || exit 1; \
	done

check: lint test ## Everything CI runs

##@ Docs

docs: ## Serve the documentation on localhost:8001
	uv run --only-group docs mkdocs serve --dev-addr localhost:8001

docs-build: ## Build the documentation into ./site
	uv run --only-group docs mkdocs build --strict

##@ Container

image: ## Build the container image locally
	$(CONTAINER_ENGINE) build -t $(IMAGE):dev .

image-run: image ## Run the locally built image
	$(CONTAINER_ENGINE) run --rm -p $(PORT):8000 \
		-v $(CURDIR)/config.yml:/app/config.yml:ro \
		--env-file .env \
		$(IMAGE):dev

##@ Release

lock: ## Refresh uv.lock
	uv lock

upgrade: ## Upgrade all locked dependencies
	uv lock --upgrade
	npm update

build: clean assets ## Build the wheel and sdist
	uv build

test-release: build ## Publish to TestPyPI
	uv publish --publish-url https://test.pypi.org/legacy/

release: build ## Publish to PyPI
	uv publish

clean: ## Remove build artefacts and caches
	rm -rf *.egg-info dist build site .venvs coverage.xml .coverage
	rm -rf vaultr/static/css vaultr/static/js
	find . -name '__pycache__' -prune -exec rm -rf {} +

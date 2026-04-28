UV ?= uv
DOCKER_COMPOSE := docker compose -f docker-compose.yml
DOCKER_COMPOSE_DEV := $(DOCKER_COMPOSE) -f docker-compose.local.yml
PYTEST := $(UV) run pytest
RUFF := $(UV) run ruff
TEST_PKG := ./scripts/test-package.py

# ---- Build metadata ---------------------------------------------------------

GIT_SHA        := $(shell git rev-parse HEAD 2>/dev/null || echo unknown)
GIT_SHORT_SHA  := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
BUILD_TIME     := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
BUILD_ID       := local-$(GIT_SHORT_SHA)

API_APP_VERSION := $(shell grep '^version' deployments/api/pyproject.toml | sed 's/.*"\(.*\)".*/\1/' || echo unknown)
FRONTEND_APP_VERSION := $(shell node -p "require('./deployments/stitch-frontend/package.json').version" 2>/dev/null || echo unknown)
# Aggregate check: can be run in parallel with -j
check: lint test format-check lock-check
	@echo "All checks passed."

lint: py-lint frontend-lint
test: py-test frontend-test
format-check: py-format-check frontend-format-check
lock-check: py-lock-check

format: py-format frontend-format
clean: clean-build py-clean-cache frontend-clean clean-docker

build-all: py-build frontend-build

clean-build:
	rm -rf build dist

# ---------------------------------------------------------------------
# Python (UV) infrastructure
# ---------------------------------------------------------------------

uv-dev: uv-sync-dev
uv-sync-dev:
	$(UV) sync --group dev --all-packages


py-lint: uv-dev
	$(RUFF) check

py-test: py-deployment-test pkg-test
py-test-exact: py-deployment-test-exact pkg-test-exact

py-deployment-test: api-test entity-linkage-test
py-deployment-test-exact: api-test-exact entity-linkage-test-exact

py-format-check: uv-dev
	$(RUFF) format --check

py-lock-check:
	$(UV) lock --check

py-format: uv-dev
	$(RUFF) format

py-clean-cache:
	rm -rf .ruff_cache .pytest_cache

py-build: api-build pkg-build

uv-sync:
	$(UV) sync

# Generic helpers
uv-test-target:
	$(UV) run --package $(PKG) --active pytest $(TEST_PATH) $(ARGS)

uv-test-target-exact:
	$(UV) run --package $(PKG) --active --exact --group dev pytest $(TEST_PATH) $(ARGS)

# ---------------------------------------------------------------------
# UV Packages
# ---------------------------------------------------------------------

pkg-build-auth:
	$(UV) build --package stitch-auth
pkg-test-auth:
	$(MAKE) uv-test-target PKG=stitch-auth TEST_PATH=packages/stitch-auth
pkg-test-exact-auth:
	$(MAKE) uv-test-target-exact PKG=stitch-auth TEST_PATH=packages/stitch-auth

pkg-build-models:
	$(UV) build --package stitch-models
pkg-test-models:
	$(MAKE) uv-test-target PKG=stitch-models TEST_PATH=packages/stitch-models
pkg-test-exact-models:
	$(MAKE) uv-test-target-exact PKG=stitch-models TEST_PATH=packages/stitch-models

pkg-build-ogsi:
	$(UV) build --package stitch-ogsi
pkg-test-ogsi:
	$(MAKE) uv-test-target PKG=stitch-ogsi TEST_PATH=packages/stitch-ogsi
pkg-test-exact-ogsi:
	$(MAKE) uv-test-target-exact PKG=stitch-ogsi TEST_PATH=packages/stitch-ogsi

pkg-build: pkg-build-auth pkg-build-models pkg-build-ogsi
pkg-test: pkg-test-auth pkg-test-models pkg-test-ogsi
pkg-test-exact: pkg-test-exact-auth pkg-test-exact-models pkg-test-exact-ogsi

# ---------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------

api-build:
	$(UV) build --package stitch-api
api-test:
	$(MAKE) uv-test-target PKG=stitch-api TEST_PATH=deployments/api
api-test-exact:
	$(MAKE) uv-test-target-exact PKG=stitch-api TEST_PATH=deployments/api

api-dev: stack-api-dev
	POSTGRES_HOST=127.0.0.1 \
	POSTGRES_USER=stitch_app \
	$(UV) run --env-file .env -- \
		uvicorn stitch.api.main:app \
		--host 0.0.0.0 \
		--port 8000 \
		--reload \
		--reload-dir deployments/api/src \
		--reload-dir packages \
		--reload-exclude '*/tests/*'

stack-api-dev:
	SEED_API_BASE_URL=http://host.docker.internal:8000/api/v1 \
	ENTITY_LINKAGE_API_BASE_URL=http://host.docker.internal:8000/api/v1 \
	VITE_GIT_SHA=$(GIT_SHA) \
	VITE_BUILD_ID=$(BUILD_ID) \
	VITE_BUILD_TIME=$(BUILD_TIME) \
	VITE_APP_VERSION=$(FRONTEND_APP_VERSION) \
	$(DOCKER_COMPOSE_DEV) \
		--profile frontend \
		--profile tools \
		--profile seed \
		--profile friends \
		up --build \
		-d

entity-linkage-build:
	$(UV) build --package stitch-entity-linkage
entity-linkage-test:
	$(MAKE) uv-test-target PKG=stitch-entity-linkage TEST_PATH=deployments/entity-linkage
entity-linkage-test-exact:
	$(MAKE) uv-test-target-exact PKG=stitch-entity-linkage TEST_PATH=deployments/entity-linkage

# ---------------------------------------------------------------------
# stitch-frontend
# ---------------------------------------------------------------------
FRONTEND_DIR := deployments/stitch-frontend
NPM := npm --prefix $(FRONTEND_DIR)

FRONTEND_PKG  := $(FRONTEND_DIR)/package.json
FRONTEND_LOCK := $(FRONTEND_DIR)/package-lock.json

FRONTEND_INSTALL_STAMP := build/frontend.npm-ci.stamp
FRONTEND_BUILD_STAMP   := build/frontend.build.stamp

# Inputs that should trigger reinstall / rebuild
FRONTEND_INSTALL_INPUTS := $(FRONTEND_PKG) $(FRONTEND_LOCK)

FRONTEND_BUILD_INPUTS := \
	$(FRONTEND_DIR)/index.html \
	$(FRONTEND_DIR)/vite.config.js \
	$(FRONTEND_DIR)/vitest.config.js \
	$(FRONTEND_DIR)/eslint.config.js \
	$(shell find $(FRONTEND_DIR)/src $(FRONTEND_DIR)/public -type f) \
	$(FRONTEND_INSTALL_INPUTS)

frontend: frontend-build

frontend-dev: $(FRONTEND_INSTALL_STAMP) stack-frontend-dev
	$(NPM) run dev

stack-frontend-dev:
	SEED_API_BASE_URL=http://api:8000/api/v1 \
	API_GIT_SHA=$(GIT_SHA) \
	API_BUILD_ID=$(BUILD_ID) \
	API_BUILD_TIME=$(BUILD_TIME) \
	API_APP_VERSION=$(API_APP_VERSION) \
	$(DOCKER_COMPOSE_DEV) \
		--profile api \
		--profile tools \
		--profile seed \
		--profile friends \
		up --build \
		-d

# --- install deps (keyed off lockfile) ---
frontend-install: $(FRONTEND_INSTALL_STAMP)

$(FRONTEND_INSTALL_STAMP): $(FRONTEND_INSTALL_INPUTS)
	mkdir -p $(@D)
	$(NPM) ci
	touch $@

# --- build (incremental) ---
frontend-build: $(FRONTEND_BUILD_STAMP)

$(FRONTEND_BUILD_STAMP): $(FRONTEND_INSTALL_STAMP) $(FRONTEND_BUILD_INPUTS)
	mkdir -p $(@D)
	$(NPM) run build
	touch $@

frontend-test: $(FRONTEND_INSTALL_STAMP)
	$(NPM) run test:run

frontend-lint: $(FRONTEND_INSTALL_STAMP)
	$(NPM) run lint

frontend-format: $(FRONTEND_INSTALL_STAMP)
	$(NPM) run format

frontend-format-check: $(FRONTEND_INSTALL_STAMP)
	$(NPM) run format:check

frontend-clean:
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules \
	       $(FRONTEND_INSTALL_STAMP) $(FRONTEND_BUILD_STAMP)

# ---------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------
clean-docker:
	$(DOCKER_COMPOSE_DEV) --profile "*" down --volumes --remove-orphans

dev-docker:
	$(DOCKER_COMPOSE_DEV) --profile full up

reboot-docker: clean-docker
	$(DOCKER_COMPOSE_DEV) --profile full up --build

follow-stack-logs:
	$(DOCKER_COMPOSE_DEV) --profile full logs -f

.PHONY: \
	# Workspace
	check lint test format format-check lock-check \
	build-all \
	clean clean-build \
	\
	# Python (uv)
	py-lint py-test py-test-exact py-format py-format-check py-lock-check py-clean-cache \
	py-build \
	uv-dev uv-sync uv-sync-dev \
	uv-test-target uv-test-target-exact \
	\
	# Packages
	pkg-test pkg-test-exact \
	pkg-build-auth pkg-test-auth pkg-test-exact-auth \
	pkg-build-models pkg-test-models pkg-test-exact-models \
	pkg-build-ogsi pkg-test-ogsi pkg-test-exact-ogsi \
	\
	# API
	api-build api-test api-test-exact api-dev stack-api-dev \
	\
	# Frontend
	frontend frontend-install frontend-build frontend-test frontend-lint \
	frontend-format frontend-format-check \
	frontend-dev frontend-clean \
	\
	# Docker
	clean-docker dev-docker reboot-docker \
	stack-frontend-dev follow-stack-logs

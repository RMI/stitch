UV ?= uv
PYTEST := $(UV) run pytest
RUFF := $(UV) run ruff

# Aggregate check: can be run in parallel with -j
check: lint test format-check
	@echo "All checks passed."

lint: uv-lint frontend-lint

test: uv-test frontend-test

format: uv-format frontend-format

format-check: uv-format-check frontend-format-check

uv-lint: uv-dev
	$(RUFF) check

uv-test: uv-dev
	$(PYTEST) packages/schema
	$(PYTEST) packages/stitch-core

uv-format: uv-dev
	$(RUFF) format

uv-format-check: uv-dev
	$(RUFF) format --check

uv-dev: uv-sync-all

uv-sync:
	$(UV) sync

uv-sync-dev:
	$(UV) sync --group dev

uv-sync-all:
	$(UV) sync --group dev --extra cli

# ---------------------------------------------------------------------
# Packages and source discovery
# ---------------------------------------------------------------------
all: build-python cli frontend
build-python: schema stitch-core
clean: clean-build clean-cache frontend-clean

clean-build:
	rm -rf build dist
clean-cache:
	rm -rf .ruff_cache .pytest_cache

SCHEMA_DIR := packages/schema
SCHEMA_SRCS := $(shell find $(SCHEMA_DIR) -name '*.py' -o -name 'pyproject.toml')
SCHEMA_STAMP := build/schema.stamp

schema: $(SCHEMA_STAMP)

$(SCHEMA_STAMP): $(SCHEMA_SRCS)
	mkdir -p $(@D)
	$(UV) build $(SCHEMA_DIR)
	touch $@

STITCHCORE_DIR := packages/stitch-core
STITCHCORE_SRCS := $(shell find $(STITCHCORE_DIR) -name '*.py' -o -name 'pyproject.toml')
STITCHCORE_STAMP := build/stitch-core.stamp

stitch-core: $(STITCHCORE_STAMP)

$(STITCHCORE_STAMP): $(STITCHCORE_SRCS) $(CLI_STAMP)
	mkdir -p $(@D)
	$(UV) build $(STITCHCORE_DIR)
	touch $@

CLI_DIR := dev/stitch-cli
CLI_SRCS := $(shell find $(CLI_DIR) -name '*.py' -o -name 'pyproject.toml')
CLI_STAMP := build/cli.stamp

cli: $(CLI_STAMP)

$(CLI_STAMP): $(CLI_SRCS)
	mkdir -p $(@D)
	$(UV) build $(CLI_DIR)
	touch $@

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

frontend-dev: $(FRONTEND_INSTALL_STAMP)
	$(NPM) run dev

frontend-clean:
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules \
	       $(FRONTEND_INSTALL_STAMP) $(FRONTEND_BUILD_STAMP)

.PHONY: all build clean \
        build-python \
        check lint test format format-check \
        uv-lint uv-test uv-format uv-format-check \
        uv-sync uv-sync-dev uv-sync-all \
        uv-dev \
        schema stitch-core cli \
        clean-build clean-cache \
        frontend frontend-install frontend-build frontend-test frontend-lint frontend-dev frontend-clean frontend-format frontend-format-check

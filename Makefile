UV ?= uv
PYTEST := $(UV) run pytest
RUFF := $(UV) run ruff

# Aggregate check: can be run in parallel with -j
check: lint test format-check
	@echo "All checks passed."

lint: dev
	$(RUFF) check

test: dev
	$(PYTEST) packages/schema
	$(PYTEST) packages/stitch-core

format: dev
	$(RUFF) format

format-check: dev
	$(RUFF) format --check

dev: sync-all

sync:
	$(UV) sync

sync-dev:
	$(UV) sync --group dev

sync-all:
	$(UV) sync --group dev --extra cli

# ---------------------------------------------------------------------
# Packages and source discovery
# ---------------------------------------------------------------------
all: build cli
build: schema stitch-core
clean: clean-build clean-cache

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

.PHONY: all build clean \
        check lint test format format-check \
        sync sync-dev sync-all \
				dev \
        schema stitch-core cli \
        clean-build clean-cache

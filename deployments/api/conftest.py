"""Suite-wide environment setup, applied before any app import.

Loaded by pytest from the rootdir before ``tests/conftest.py`` (which imports
the app, and the app configures OpenTelemetry tracing at import time).

Tracing is process-global and emits span records to stdout on every request;
the unit/integration suite doesn't exercise it, and benchmarking/trace
verification runs against real infrastructure instead. Disable it here. Override
by exporting ``OTEL_TRACES_EXPORTER=console`` when debugging tracing locally.

The settings classes read a ``.env`` file relative to the working directory.
``make`` runs the suite from the repo root, so ``Settings()`` would otherwise
pick up a developer's local ``.env`` and mask the declared code defaults that
tests assert against. Disable dotenv loading so tests see defaults plus the
explicit process env above; real env vars still win via ``os.environ``.
"""

import os

from stitch.api.settings import PostgresConfig, Settings, SqliteConfig

os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")

for _settings_cls in (Settings, PostgresConfig, SqliteConfig):
    _settings_cls.model_config["env_file"] = None

"""Suite-wide environment setup, applied before any app import.

Loaded by pytest from the rootdir before ``tests/conftest.py`` (which imports
the app, and the app configures OpenTelemetry tracing at import time).

Tracing is process-global and emits span records to stdout on every request;
the unit/integration suite doesn't exercise it, and benchmarking/trace
verification runs against real infrastructure instead. Disable it here. Override
by exporting ``OTEL_TRACES_EXPORTER=console`` when debugging tracing locally.
"""

import os

os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")

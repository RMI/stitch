import os

# Disable tracing for the suite before the app module imports and runs
# configure_tracing (mirrors the API's rootdir conftest). An env var set here
# wins over the .env file's value via pydantic-settings precedence.
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")

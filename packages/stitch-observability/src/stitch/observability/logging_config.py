"""Shared structured logging for Stitch services.

Installs a single stdout handler on the root logger with a JSON formatter, so
the per-request / per-query events (and the span records emitted by
:class:`~stitch.observability.tracing.LoggingSpanExporter`) are machine-parseable
in Log Analytics. Optionally stamps a fixed set of resource attributes
(``deployment.name``, ``service.version``, ...) onto every record so logs carry
the same deployment metadata as trace spans and can be sliced/compared across
deployments and PRs.
"""

import json
import logging
import os
import sys
from collections.abc import Mapping
from typing import Literal

LogFormat = Literal["json", "plain"]

# Standard LogRecord attributes; everything else attached via ``extra`` is
# treated as part of the structured payload.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}

_PLAIN_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


class JsonFormatter(logging.Formatter):
    """Render each record as a single JSON object.

    The ``event`` dict attached by the sinks is flattened into the top level so
    fields like ``duration_ms`` and ``route`` are directly queryable.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload.update(event)

        # Pick up any other ad-hoc ``extra`` fields (incl. the resource
        # attributes stamped by ResourceAttributesFilter) without clobbering
        # core keys.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "event" and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class ResourceAttributesFilter(logging.Filter):
    """Stamp a fixed set of attributes onto every record.

    Used to attach deployment/environment metadata (``deployment.name``,
    ``service.version``, ...) so structured logs carry the same tags as trace
    resource attributes. A record that already carries a key (e.g. set via
    ``extra``) is left untouched, so per-event values win over the static tags.
    """

    def __init__(self, attributes: Mapping[str, str]) -> None:
        super().__init__()
        self._attributes = dict(attributes)

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self._attributes.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def resource_attributes_from_env() -> dict[str, str]:
    """Parse the same OTEL env vars the tracing SDK reads into a flat dict.

    Reads ``OTEL_SERVICE_NAME`` and the comma-separated ``OTEL_RESOURCE_ATTRIBUTES``
    (``key=value,key=value``). Sharing this source means logs and trace spans
    carry identical deployment tags. Malformed pairs (no ``=``) are skipped.
    """
    attributes: dict[str, str] = {}
    service_name = os.getenv("OTEL_SERVICE_NAME")
    if service_name:
        attributes["service.name"] = service_name
    for pair in os.getenv("OTEL_RESOURCE_ATTRIBUTES", "").split(","):
        key, sep, value = pair.partition("=")
        key, value = key.strip(), value.strip()
        if sep and key:
            attributes[key] = value
    return attributes


def configure_logging(
    *,
    level: str | None = None,
    log_format: LogFormat = "json",
    resource_attributes: Mapping[str, str] | None = None,
) -> None:
    """Install a single stdout handler on the root logger.

    Called once at startup. Safe to call again (it replaces handlers).
    ``uvicorn`` does not pass ``--log-config``, so configuring the root logger
    here wins; we also stop uvicorn's loggers from carrying their own handlers
    and quiet its per-request access log (a request middleware emits a richer
    summary). When ``resource_attributes`` is given, every record is stamped
    with those key/values (deployment metadata) via a handler filter.
    """
    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    resolved = getattr(logging, level_name, logging.INFO)

    # Explicitly stdout: StreamHandler() defaults to stderr, which would
    # contradict the docstring and break stdout-only capture pipelines.
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))
    if resource_attributes:
        handler.addFilter(ResourceAttributesFilter(resource_attributes))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(resolved)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    # Our request middleware logs every request; uvicorn's access log would
    # just duplicate that, so keep it quiet.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

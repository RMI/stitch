"""Logging setup for the API.

Despite ``LOG_LEVEL`` being passed to every container, the API never
configured logging — only the ``seed`` service did. This wires it up and adds a
JSON formatter so the per-query / per-request events emitted via
:mod:`sinks` are machine-parseable in Log Analytics.
"""

import json
import logging
import os
from typing import Literal

# Standard LogRecord attributes; everything else attached via ``extra`` is
# treated as part of the structured payload.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}

LogFormat = Literal["json", "plain"]


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

        # Pick up any other ad-hoc ``extra`` fields without clobbering core keys.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "event" and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


_PLAIN_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(
    *,
    level: str | None = None,
    log_format: LogFormat = "json",
) -> None:
    """Install a single stdout handler on the root logger.

    Called once at import time. Safe to call again (it replaces handlers).
    ``uvicorn`` does not pass ``--log-config``, so configuring the root logger
    here wins; we also stop uvicorn's loggers from carrying their own handlers
    and quiet its per-request access log (our request middleware emits a richer
    summary).
    """
    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    resolved = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))

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

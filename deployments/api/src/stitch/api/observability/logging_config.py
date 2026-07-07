"""Logging setup for the API — a thin wrapper over the shared
``stitch.observability`` logging (one source of truth across services).

Re-exports ``configure_logging`` / ``JsonFormatter`` / ``resource_attributes_from_env``
so existing call sites and tests are unchanged. The per-query / per-request
events emitted via :mod:`sinks` are flattened by the shared ``JsonFormatter``
and stamped with deployment metadata when ``main`` passes
``resource_attributes`` (see :func:`resource_attributes_from_env`).
"""

from stitch.observability import (
    JsonFormatter,
    configure_logging,
    resource_attributes_from_env,
)

__all__ = ["JsonFormatter", "configure_logging", "resource_attributes_from_env"]

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class OTelSettings(BaseSettings):
    """Mixin of the shared ``OTEL_*`` tracing settings.

    A service's ``Settings`` inherits this so every service reads the same env
    (``OTEL_ENABLED`` / ``OTEL_TRACES_EXPORTER`` / ``OTEL_EXPORTER_OTLP_ENDPOINT``
    / ``OTEL_EXPORTER_OTLP_PROTOCOL`` / ``OTEL_SAMPLE_RATIO``), which are already
    shared across the compose network.

    Defaults: ``console`` exporter logs spans to stdout (no collector needed);
    ``otlp`` ships to the collector (gRPC or HTTP per ``otel_exporter_otlp_protocol``);
    ``none`` disables tracing. ``otel_sample_ratio`` feeds the root sampler
    (1.0 = capture everything); downstream spans honor the upstream decision via
    ParentBased.
    """

    otel_enabled: bool = True
    otel_traces_exporter: Literal["console", "otlp", "none"] = "console"
    otel_exporter_otlp_endpoint: str | None = None
    otel_exporter_otlp_protocol: Literal["grpc", "http"] = "grpc"
    otel_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

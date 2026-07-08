"""Tests for the OpenTelemetry tracing setup.

These exercise the tracing module directly (its own provider + exporter) rather
than the global provider the app installs at import, so they are independent of
process-wide tracer state and of whatever ``OTEL_*`` env the suite runs under.
"""

import logging

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode
from pydantic import ValidationError

from stitch.api.observability.tracing import LoggingSpanExporter, configure_tracing
from stitch.api.settings import Settings

# The exporter now lives in the shared stitch-observability package and logs
# under its own logger name; the API shim re-exports it unchanged.
_TRACE_LOGGER = "stitch.observability.trace"


@pytest.fixture
def logging_tracer():
    """A tracer wired to the LoggingSpanExporter via a local provider."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(LoggingSpanExporter()))
    yield provider.get_tracer("test")
    provider.shutdown()


def _trace_events(caplog) -> list[dict]:
    return [r.event for r in caplog.records if r.name == _TRACE_LOGGER]


class TestLoggingSpanExporter:
    def test_emits_one_record_per_span_with_core_fields(self, logging_tracer, caplog):
        with caplog.at_level(logging.INFO, logger=_TRACE_LOGGER):
            with logging_tracer.start_as_current_span("my-span") as span:
                span.set_attribute("stitch.request_id", "abc123")

        events = _trace_events(caplog)
        assert len(events) == 1
        event = events[0]
        assert event["span_name"] == "my-span"
        assert event["kind"] == SpanKind.INTERNAL.name
        assert len(event["trace_id"]) == 32
        assert len(event["span_id"]) == 16
        assert event["parent_span_id"] is None
        assert event["duration_ms"] is not None
        assert event["status"] == StatusCode.UNSET.name
        assert event["attributes"]["stitch.request_id"] == "abc123"

    def test_child_span_records_parent_and_shares_trace(self, logging_tracer, caplog):
        with caplog.at_level(logging.INFO, logger=_TRACE_LOGGER):
            with logging_tracer.start_as_current_span("parent"):
                with logging_tracer.start_as_current_span("child"):
                    pass

        by_name = {e["span_name"]: e for e in _trace_events(caplog)}
        assert by_name["child"]["parent_span_id"] == by_name["parent"]["span_id"]
        assert by_name["child"]["trace_id"] == by_name["parent"]["trace_id"]


class TestConfigureTracing:
    def test_returns_none_when_disabled(self):
        assert configure_tracing(Settings(otel_enabled=False)) is None

    def test_returns_none_when_exporter_is_none(self):
        assert configure_tracing(Settings(otel_traces_exporter="none")) is None

    def test_console_exporter_returns_provider(self, monkeypatch):
        # Stub set_tracer_provider so this exercises only provider construction
        # and leaves the process-global provider untouched (OTel makes it
        # set-once and won't cleanly reset). The shim delegates to the package,
        # so the call to patch lives there.
        import stitch.observability.tracing as pkg_tracing

        monkeypatch.setattr(pkg_tracing.trace, "set_tracer_provider", lambda _p: None)
        # Set both fields explicitly so the test controls its inputs rather than
        # inheriting otel_enabled from the ambient .env (which may disable it).
        provider = configure_tracing(
            Settings(otel_enabled=True, otel_traces_exporter="console")
        )
        try:
            assert provider is not None
        finally:
            if provider is not None:
                provider.shutdown()

    @pytest.mark.parametrize("ratio", [-0.1, 1.5])
    def test_sample_ratio_out_of_range_is_rejected(self, ratio):
        # TraceIdRatioBased is only defined on [0, 1]; an invalid env value
        # should fail fast at settings construction, not silently misbehave.
        with pytest.raises(ValidationError):
            Settings(otel_sample_ratio=ratio)

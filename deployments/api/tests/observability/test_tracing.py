"""Tests for the OpenTelemetry tracing setup.

These exercise the tracing module directly (its own provider + exporter) rather
than the global provider the app installs at import, so they are independent of
process-wide tracer state and of whatever ``OTEL_*`` env the suite runs under.
"""

import logging

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from stitch.api.observability.tracing import LoggingSpanExporter, configure_tracing
from stitch.api.settings import Settings

_TRACE_LOGGER = "stitch.api.observability.trace"


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
        assert event["kind"] == "INTERNAL"
        assert len(event["trace_id"]) == 32
        assert len(event["span_id"]) == 16
        assert event["parent_span_id"] is None
        assert event["duration_ms"] is not None
        assert event["status"] == "UNSET"
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

    def test_console_exporter_returns_provider(self):
        provider = configure_tracing(Settings(otel_traces_exporter="console"))
        try:
            assert provider is not None
        finally:
            if provider is not None:
                provider.shutdown()

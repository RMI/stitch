import logging

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from stitch.observability import (
    OTelSettings,
    configure_tracing,
    setup_fastapi_tracing,
    setup_sqlalchemy_tracing,
)
from stitch.observability import tracing as pkg_tracing
from stitch.observability.tracing import LoggingSpanExporter


def test_configure_tracing_disabled_returns_none() -> None:
    assert configure_tracing(service_name="svc", enabled=False) is None
    assert configure_tracing(service_name="svc", enabled=True, exporter="none") is None


def test_configure_tracing_builds_provider_with_resource(monkeypatch) -> None:
    # configure_tracing installs the provider globally via set_tracer_provider;
    # stub that out so this test exercises only provider construction and leaves
    # the process-global provider untouched (OTel makes it set-once).
    monkeypatch.setattr(trace, "set_tracer_provider", lambda _provider: None)
    provider = configure_tracing(
        service_name="stitch-test",
        exporter="console",
        version="1.2.3",
        environment="test",
    )
    assert isinstance(provider, TracerProvider)
    attrs = provider.resource.attributes
    assert attrs["service.name"] == "stitch-test"
    assert attrs["service.version"] == "1.2.3"
    assert attrs["deployment.environment"] == "test"


def test_configure_tracing_omits_missing_keys_so_env_wins(monkeypatch) -> None:
    # With version/environment unset they are omitted, so env-provided
    # OTEL_RESOURCE_ATTRIBUTES survive Resource.create()'s merge — this is the
    # deployment-tagging path (deployment.name set once in CI, stamped on spans).
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.name=pr-7")
    monkeypatch.setattr(trace, "set_tracer_provider", lambda _provider: None)
    provider = configure_tracing(service_name="svc", exporter="console")
    attrs = provider.resource.attributes
    assert attrs["service.name"] == "svc"
    assert attrs["deployment.name"] == "pr-7"
    assert "service.version" not in attrs


def test_configure_tracing_merges_extra_resource_attributes(monkeypatch) -> None:
    monkeypatch.setattr(trace, "set_tracer_provider", lambda _provider: None)
    provider = configure_tracing(
        service_name="svc",
        exporter="console",
        extra_resource_attributes={"deployment.lane": "development"},
    )
    assert provider.resource.attributes["deployment.lane"] == "development"


def test_setup_fastapi_tracing_disabled_skips_instrumentation(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(pkg_tracing, "instrument_fastapi", lambda _app: calls.append("fastapi"))
    monkeypatch.setattr(pkg_tracing, "instrument_httpx", lambda: calls.append("httpx"))
    provider = setup_fastapi_tracing(
        object(),
        service_name="svc",
        settings=OTelSettings(otel_traces_exporter="none"),
    )
    assert provider is None
    assert calls == []


def test_setup_fastapi_tracing_instruments_app_and_httpx(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(pkg_tracing.trace, "set_tracer_provider", lambda _p: None)
    monkeypatch.setattr(pkg_tracing, "instrument_fastapi", lambda _app: calls.append("fastapi"))
    monkeypatch.setattr(pkg_tracing, "instrument_httpx", lambda: calls.append("httpx"))
    provider = setup_fastapi_tracing(
        object(),
        service_name="svc",
        settings=OTelSettings(otel_traces_exporter="console"),
    )
    assert provider is not None
    assert calls == ["fastapi", "httpx"]


def test_setup_fastapi_tracing_can_skip_outbound_httpx(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(pkg_tracing.trace, "set_tracer_provider", lambda _p: None)
    monkeypatch.setattr(pkg_tracing, "instrument_fastapi", lambda _app: calls.append("fastapi"))
    monkeypatch.setattr(pkg_tracing, "instrument_httpx", lambda: calls.append("httpx"))
    setup_fastapi_tracing(
        object(),
        service_name="svc",
        settings=OTelSettings(otel_traces_exporter="console"),
        instrument_outbound_httpx=False,
    )
    assert calls == ["fastapi"]


def test_setup_sqlalchemy_tracing_noop_when_disabled(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(pkg_tracing, "instrument_sqlalchemy", lambda e: calls.append(e))
    assert (
        setup_sqlalchemy_tracing(
            object(), settings=OTelSettings(otel_traces_exporter="none")
        )
        is False
    )
    assert (
        setup_sqlalchemy_tracing(object(), settings=OTelSettings(otel_enabled=False))
        is False
    )
    assert calls == []


def test_setup_sqlalchemy_tracing_instruments_when_enabled(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(pkg_tracing, "instrument_sqlalchemy", lambda e: calls.append(e))
    engine = object()
    assert (
        setup_sqlalchemy_tracing(
            engine, settings=OTelSettings(otel_traces_exporter="console")
        )
        is True
    )
    assert calls == [engine]


def test_logging_span_exporter_emits_one_record_per_span(caplog) -> None:
    # A local provider + the exporter under test; never touches the global.
    exporter = LoggingSpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    with caplog.at_level(logging.INFO, logger="stitch.observability.trace"):
        with tracer.start_as_current_span("unit-span"):
            pass

    records = [r for r in caplog.records if r.name == "stitch.observability.trace"]
    assert len(records) == 1
    assert records[0].event["span_name"] == "unit-span"
    assert "trace_id" in records[0].event
    # Resource attributes are emitted so the stdout span stream carries the same
    # deployment tags as the OTLP path.
    assert "resource" in records[0].event


def test_logging_span_exporter_truncates_long_attributes(caplog) -> None:
    # An over-long attribute (e.g. a big SQLAlchemy db.statement) is capped so a
    # single span log record can't dump an unbounded string to stdout.
    exporter = LoggingSpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    long_value = "x" * 5000
    with caplog.at_level(logging.INFO, logger="stitch.observability.trace"):
        with tracer.start_as_current_span("big-span") as span:
            span.set_attribute("db.statement", long_value)

    records = [r for r in caplog.records if r.name == "stitch.observability.trace"]
    logged = records[0].event["attributes"]["db.statement"]
    assert logged.endswith("…")
    assert len(logged) == 2000 + 1  # 2000-char cap + the ellipsis


def test_otel_settings_defaults_and_bounds() -> None:
    s = OTelSettings()
    assert s.otel_enabled is True
    assert s.otel_traces_exporter == "console"
    assert s.otel_sample_ratio == 1.0
    assert OTelSettings(otel_sample_ratio=0.25).otel_sample_ratio == 0.25


def test_in_memory_exporter_captures_spans() -> None:
    # Demonstrates the local-provider pattern the jobs trace test uses.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("t").start_span("s").end()
    assert [s.name for s in exporter.get_finished_spans()] == ["s"]

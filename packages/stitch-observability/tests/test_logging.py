import json
import logging

from stitch.observability import (
    JsonFormatter,
    ResourceAttributesFilter,
    resource_attributes_from_env,
)


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_resource_attributes_from_env_parses_service_and_attrs(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "stitch-api")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES", "deployment.name=pr-7,deployment.lane=development"
    )
    attrs = resource_attributes_from_env()
    assert attrs == {
        "service.name": "stitch-api",
        "deployment.name": "pr-7",
        "deployment.lane": "development",
    }


def test_resource_attributes_from_env_skips_malformed_and_empty(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "good=1,,bogus,=novalue,also.good=2")
    attrs = resource_attributes_from_env()
    assert attrs == {"good": "1", "also.good": "2"}


def test_resource_attributes_from_env_empty_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
    assert resource_attributes_from_env() == {}


def test_resource_attributes_filter_stamps_record() -> None:
    record = _record()
    ResourceAttributesFilter({"deployment.name": "pr-7"}).filter(record)
    assert getattr(record, "deployment.name") == "pr-7"


def test_resource_attributes_filter_does_not_clobber_existing() -> None:
    # A per-event value (e.g. via extra=) wins over the static resource tag.
    record = _record(**{"deployment.name": "per-event"})
    ResourceAttributesFilter({"deployment.name": "static"}).filter(record)
    assert getattr(record, "deployment.name") == "per-event"


def test_json_formatter_includes_stamped_resource_attribute() -> None:
    record = _record()
    ResourceAttributesFilter({"deployment.name": "pr-7"}).filter(record)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["deployment.name"] == "pr-7"
    assert payload["msg"] == "hello"


def test_json_formatter_flattens_event_dict() -> None:
    record = _record(event={"duration_ms": 12.5, "route": "/x"})
    payload = json.loads(JsonFormatter().format(record))
    assert payload["duration_ms"] == 12.5
    assert payload["route"] == "/x"


def test_json_formatter_event_does_not_clobber_core_keys() -> None:
    # A stray event key colliding with a core field (ts/level/logger/msg) must
    # not overwrite it — the core keys define the log schema.
    record = _record(event={"level": "SPOOFED", "msg": "spoofed", "route": "/x"})
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["msg"] == "hello"
    assert payload["route"] == "/x"

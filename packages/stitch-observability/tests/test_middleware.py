import importlib
import logging
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stitch.observability import middleware as mw
from stitch.observability.middleware import RequestContextMiddleware


def _make_app(middleware_cls=RequestContextMiddleware) -> FastAPI:
    app = FastAPI()
    app.add_middleware(middleware_cls)

    @app.get("/things/{thing_id}")
    async def get_thing(thing_id: int):
        return {"id": thing_id}

    return app


def _request_events(caplog) -> list[dict]:
    return [r.event for r in caplog.records if r.name == "stitch.observability.request"]


def test_emits_summary_and_sets_request_id_header(caplog) -> None:
    client = TestClient(_make_app())
    with caplog.at_level(logging.INFO, logger="stitch.observability.request"):
        response = client.get("/things/42")

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert request_id

    events = _request_events(caplog)
    assert len(events) == 1
    event = events[0]
    assert event["request_id"] == request_id
    assert event["method"] == "GET"
    assert event["route"] == "/things/{thing_id}"
    assert event["status_code"] == 200
    assert event["duration_ms"] >= 0
    assert event["scenario"] is None


def test_scenario_header_is_captured_and_truncated(caplog) -> None:
    client = TestClient(_make_app())
    with caplog.at_level(logging.INFO, logger="stitch.observability.request"):
        client.get("/things/1", headers={"X-Stitch-Perf-Scenario": "x" * 200})

    assert len(_request_events(caplog)[-1]["scenario"]) == 80


def test_subclass_hooks_add_fields(caplog) -> None:
    # Validates the extension contract the API's RequestTimingMiddleware will use
    # to graft on its DB aggregates without reimplementing the request-id / span
    # / logging plumbing.
    finished: list[object] = []

    class WithExtras(RequestContextMiddleware):
        def on_request_start(self, request):
            return {"widgets": 3}

        def request_log_fields(self, state):
            return {"widget_count": state["widgets"]}

        def on_request_finish(self, state):
            finished.append(state)

    client = TestClient(_make_app(WithExtras))
    with caplog.at_level(logging.INFO, logger="stitch.observability.request"):
        client.get("/things/7")

    assert _request_events(caplog)[-1]["widget_count"] == 3
    assert finished == [{"widgets": 3}]


def test_context_vars_reset_after_request() -> None:
    # The middleware resets the context vars in its finally block; outside a
    # request they read their defaults.
    client = TestClient(_make_app())
    client.get("/things/1")
    assert mw.request_id_var.get() is None
    assert mw.route_var.get() is None
    assert mw.scenario_var.get() is None


@pytest.mark.parametrize("raising_hook", ["on_request_start", "request_log_fields"])
def test_context_vars_reset_when_a_hook_raises(raising_hook) -> None:
    # A raising subclass hook must not leak request context: the resets live in
    # an outer finally so request_id/route/scenario return to their defaults even
    # when the hook blows up mid-request.
    class Boom(RequestContextMiddleware):
        def on_request_start(self, request):
            if raising_hook == "on_request_start":
                raise RuntimeError("boom")
            return None

        def request_log_fields(self, state):
            if raising_hook == "request_log_fields":
                raise RuntimeError("boom")
            return {}

    client = TestClient(_make_app(Boom))
    with pytest.raises(RuntimeError, match="boom"):
        client.get("/things/1")

    assert mw.request_id_var.get() is None
    assert mw.route_var.get() is None
    assert mw.scenario_var.get() is None


def test_middleware_import_without_starlette_points_at_asgi_extra(monkeypatch) -> None:
    # Starlette is an optional `asgi` extra, guarded at the middleware's top-level
    # import. Simulate a consumer that installed stitch-observability WITHOUT the
    # extra and assert the import fails with a message naming the extra, not a
    # bare ModuleNotFoundError. All sys.modules edits go through monkeypatch so
    # they're restored at teardown and the suite stays order-independent.

    # Force the guarded imports to run again on re-import.
    monkeypatch.delitem(sys.modules, "stitch.observability.middleware", raising=False)
    # Make `import starlette` fail: drop cached submodules and point the parent at
    # None — the canonical way to make an installed package look absent.
    for name in list(sys.modules):
        if name == "starlette" or name.startswith("starlette."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "starlette", None)

    with pytest.raises(ModuleNotFoundError, match=r"stitch-observability\[asgi\]"):
        importlib.import_module("stitch.observability.middleware")

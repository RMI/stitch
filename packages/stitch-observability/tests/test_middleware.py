import logging

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

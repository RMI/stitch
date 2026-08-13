"""Tests for the batch-yield admission gate.

Timing behavior is driven by an injected clock and sleep rather than the wall
clock, so nothing here waits in real time. The one test that depends on genuine
concurrency (a batch request blocked by an interactive request still in flight)
asserts on *ordering* — whether the batch task has completed — rather than on any
elapsed duration.
"""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.cors import CORSMiddleware

from stitch.api.admission import (
    BATCH_TRAFFIC_CLASS,
    TRAFFIC_CLASS_HEADER,
    BatchYieldMiddleware,
    InteractiveActivity,
    _is_batch,
    _is_exempt,
)
from stitch.api.main import create_app
from stitch.api.observability import RequestTimingMiddleware
from stitch.api.settings import Settings

_GATE_LOGGER = "stitch.api.admission"
_BATCH_HEADERS = {TRAFFIC_CLASS_HEADER: BATCH_TRAFFIC_CLASS}


def _gate_events(caplog) -> list[dict]:
    return [r.event for r in caplog.records if r.name == _GATE_LOGGER]


class FakeClock:
    """Monotonic clock that only advances when the injected sleep is awaited.

    Lets ``_wait_for_quiet`` reach its deadline deterministically: each polled
    sleep moves time forward by exactly the requested amount.
    """

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        # Must still yield to the loop. Advancing a counter is not suspension,
        # and without this the gate's poll loop spins without ever letting a
        # concurrent interactive request finish — i.e. it hangs.
        await asyncio.sleep(0)


def _http_scope(
    path: str = "/api/v1/oil-gas-fields/",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
    }


class TestInteractiveActivity:
    def test_fresh_activity_is_quiet(self) -> None:
        # The -inf sentinel must read as "infinitely long ago", since
        # monotonic()'s epoch is arbitrary and 0.0 would be a real timestamp.
        activity = InteractiveActivity()
        assert activity.is_quiet(quiet_s=1.5, now=0.0) is True
        assert activity.is_quiet(quiet_s=1.5, now=1_000_000.0) is True

    def test_not_quiet_while_request_in_flight(self) -> None:
        activity = InteractiveActivity()
        activity.in_flight = 1
        # In flight beats any amount of elapsed time.
        assert activity.is_quiet(quiet_s=0.0, now=1_000_000.0) is False

    def test_not_quiet_within_quiet_period(self) -> None:
        activity = InteractiveActivity()
        activity.last_finished_at = 100.0
        assert activity.is_quiet(quiet_s=1.5, now=100.5) is False

    def test_quiet_once_period_elapses(self) -> None:
        activity = InteractiveActivity()
        activity.last_finished_at = 100.0
        assert activity.is_quiet(quiet_s=1.5, now=101.5) is True


class TestClassification:
    def test_missing_header_is_interactive(self) -> None:
        assert _is_batch(_http_scope()) is False

    @pytest.mark.parametrize("raw", [b"batch", b"BATCH", b" batch ", b"Batch"])
    def test_batch_header_is_recognized(self, raw: bytes) -> None:
        scope = _http_scope(headers=[(b"x-stitch-traffic-class", raw)])
        assert _is_batch(scope) is True

    @pytest.mark.parametrize("raw", [b"", b"interactive", b"urgent", b"0", b"low"])
    def test_unrecognized_value_is_interactive(self, raw: bytes) -> None:
        # Only an explicit self-downgrade counts; anything else is interactive.
        scope = _http_scope(headers=[(b"x-stitch-traffic-class", raw)])
        assert _is_batch(scope) is False


class TestExemptions:
    @pytest.mark.parametrize(
        "path", ["/api/v1/health", "/api/v1/health/details", "/api/v1/health/deep"]
    )
    def test_health_paths_are_exempt(self, path: str) -> None:
        assert _is_exempt(path) is True

    @pytest.mark.parametrize(
        "path", ["/api/v1/healthy", "/api/v1/oil-gas-fields/", "/api/v1/healthcheck"]
    )
    def test_other_paths_are_not_exempt(self, path: str) -> None:
        # Prefix-adjacent paths must not be swept in by a loose startswith.
        assert _is_exempt(path) is False


@pytest.fixture
def gated():
    """A FastAPI app wrapped directly by the gate, exposing the gate instance.

    Wrapping by hand (rather than ``add_middleware``) gives the tests a handle on
    the single ``BatchYieldMiddleware`` instance so they can assert on its
    accounting. Production order is covered separately in
    ``TestRegistration``.
    """
    clock = FakeClock()
    app = FastAPI()
    release = asyncio.Event()
    entered = asyncio.Event()

    @app.get("/api/v1/things")
    async def things():
        return {"ok": True}

    @app.get("/api/v1/slow")
    async def slow():
        entered.set()
        await release.wait()
        return {"ok": True}

    @app.get("/api/v1/boom")
    async def boom():
        raise RuntimeError("boom")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    def build(quiet_s: float = 1.5, max_wait_s: float = 5.0) -> BatchYieldMiddleware:
        return BatchYieldMiddleware(
            app,
            quiet_s=quiet_s,
            max_wait_s=max_wait_s,
            clock=clock,
            sleep=clock.sleep,
        )

    return build, clock, entered, release


def _client(gate) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=gate), base_url="http://test")


class TestInteractiveTraffic:
    @pytest.mark.anyio
    async def test_interactive_request_is_never_delayed_or_logged(
        self, gated, caplog
    ) -> None:
        build, clock, _entered, _release = gated
        gate = build()

        with caplog.at_level(logging.INFO, logger=_GATE_LOGGER):
            async with _client(gate) as ac:
                response = await ac.get("/api/v1/things")

        assert response.status_code == 200
        assert clock.sleeps == []
        assert _gate_events(caplog) == []

    @pytest.mark.anyio
    async def test_interactive_request_updates_accounting(self, gated) -> None:
        build, clock, _entered, _release = gated
        gate = build()

        async with _client(gate) as ac:
            await ac.get("/api/v1/things")

        assert gate.activity.in_flight == 0
        assert gate.activity.last_finished_at == clock.now

    @pytest.mark.anyio
    async def test_in_flight_released_when_handler_raises(self, gated) -> None:
        # Regression guard for the try/finally: a leak here wedges the gate shut
        # for the life of the process.
        build, _clock, _entered, _release = gated
        gate = build()

        with pytest.raises(RuntimeError):
            async with _client(gate) as ac:
                await ac.get("/api/v1/boom")

        assert gate.activity.in_flight == 0
        assert gate.activity.last_finished_at != float("-inf")

    @pytest.mark.anyio
    async def test_in_flight_released_when_request_cancelled(self, gated) -> None:
        # Covers a client disconnect, which surfaces as CancelledError.
        build, _clock, entered, _release = gated
        gate = build()

        async with _client(gate) as ac:
            task = asyncio.create_task(ac.get("/api/v1/slow"))
            await entered.wait()
            assert gate.activity.in_flight == 1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert gate.activity.in_flight == 0


class TestBatchTraffic:
    @pytest.mark.anyio
    async def test_batch_passes_immediately_on_idle_server(self, gated, caplog) -> None:
        # The quiet check runs before the first sleep, so an idle server adds no
        # latency at all — the poll interval is not a settling delay.
        build, clock, _entered, _release = gated
        gate = build()

        with caplog.at_level(logging.INFO, logger=_GATE_LOGGER):
            async with _client(gate) as ac:
                response = await ac.get("/api/v1/things", headers=_BATCH_HEADERS)

        assert response.status_code == 200
        assert clock.sleeps == []
        assert _gate_events(caplog) == []

    @pytest.mark.anyio
    async def test_batch_waits_within_quiet_window_then_proceeds(
        self, gated, caplog
    ) -> None:
        build, clock, _entered, _release = gated
        gate = build(quiet_s=1.5, max_wait_s=5.0)
        # An interactive request just finished, so the window is still closed.
        gate.activity.last_finished_at = clock.now

        with caplog.at_level(logging.INFO, logger=_GATE_LOGGER):
            async with _client(gate) as ac:
                response = await ac.get("/api/v1/things", headers=_BATCH_HEADERS)

        assert response.status_code == 200
        assert clock.sleeps, "expected the batch request to have waited"
        events = _gate_events(caplog)
        assert len(events) == 1
        assert events[0]["outcome"] == "interactive_idle"
        # Released at the floor, with at most one poll interval of overshoot.
        assert 1500.0 <= events[0]["gate_wait_ms"] < 1600.0

    @pytest.mark.anyio
    async def test_batch_is_admitted_after_max_wait(self, gated, caplog) -> None:
        build, clock, _entered, _release = gated
        # quiet_s far larger than max_wait_s, so the window never opens.
        gate = build(quiet_s=1000.0, max_wait_s=0.2)
        gate.activity.last_finished_at = clock.now

        with caplog.at_level(logging.INFO, logger=_GATE_LOGGER):
            async with _client(gate) as ac:
                response = await ac.get("/api/v1/things", headers=_BATCH_HEADERS)

        # Admitted anyway, never shed — this design cannot fail a linkage run.
        assert response.status_code == 200
        events = _gate_events(caplog)
        assert len(events) == 1
        assert events[0]["outcome"] == "max_wait_exceeded"
        assert events[0]["gate_wait_ms"] >= 200.0

    @pytest.mark.anyio
    async def test_batch_waits_while_interactive_request_in_flight(self, gated) -> None:
        # The load-bearing test: assert on ordering, not elapsed time.
        build, _clock, entered, release = gated
        gate = build(quiet_s=0.0, max_wait_s=1000.0)

        async with _client(gate) as interactive_client, _client(gate) as batch_client:
            slow = asyncio.create_task(interactive_client.get("/api/v1/slow"))
            await entered.wait()
            assert gate.activity.in_flight == 1

            batch = asyncio.create_task(
                batch_client.get("/api/v1/things", headers=_BATCH_HEADERS)
            )
            # Give the batch task room to run; it must still be blocked.
            for _ in range(10):
                await asyncio.sleep(0)
            assert not batch.done(), "batch request ran while interactive was in flight"

            release.set()
            assert (await slow).status_code == 200
            assert (await batch).status_code == 200


class TestRealClockWiring:
    """One wall-clock test, to prove the *default* clock/sleep are wired up.

    Every other timing test injects a fake clock, so without this a typo in the
    default arguments would go unnoticed. Values are tens of milliseconds.
    """

    @pytest.mark.anyio
    async def test_batch_actually_waits_with_default_clock_and_sleep(self) -> None:
        app = FastAPI()

        @app.get("/api/v1/things")
        async def things():
            return {"ok": True}

        gate = BatchYieldMiddleware(app, quiet_s=0.08, max_wait_s=5.0)

        async with _client(gate) as ac:
            # An interactive request closes the window, so the batch request that
            # follows has to wait out the real quiet period.
            await ac.get("/api/v1/things")
            start = asyncio.get_running_loop().time()
            response = await ac.get("/api/v1/things", headers=_BATCH_HEADERS)
            elapsed = asyncio.get_running_loop().time() - start

        assert response.status_code == 200
        assert elapsed >= 0.05, f"batch request was not delayed (took {elapsed:.3f}s)"


class TestHealthExemption:
    @pytest.mark.anyio
    async def test_batch_health_is_never_gated(self, gated) -> None:
        build, clock, _entered, _release = gated
        # Window permanently closed for anything that is actually gated.
        gate = build(quiet_s=1000.0, max_wait_s=1000.0)
        gate.activity.last_finished_at = clock.now

        async with _client(gate) as ac:
            response = await ac.get("/api/v1/health", headers=_BATCH_HEADERS)

        assert response.status_code == 200
        assert clock.sleeps == []

    @pytest.mark.anyio
    async def test_health_is_not_counted_as_interactive(self, gated) -> None:
        # If the every-5s healthcheck bumped last_finished_at, any quiet_ms above
        # ~5000 would starve batch traffic forever with no human load at all.
        build, _clock, _entered, _release = gated
        gate = build()

        async with _client(gate) as ac:
            await ac.get("/api/v1/health")

        assert gate.activity.in_flight == 0
        assert gate.activity.last_finished_at == float("-inf")


class TestNonHttpScope:
    @pytest.mark.anyio
    async def test_non_http_scope_passes_through_without_accounting(self) -> None:
        seen: list[str] = []

        async def stub(scope, receive, send) -> None:
            seen.append(scope["type"])

        gate = BatchYieldMiddleware(stub, quiet_s=1.5, max_wait_s=5.0)
        await gate({"type": "lifespan"}, None, None)

        assert seen == ["lifespan"]
        assert gate.activity.in_flight == 0
        assert gate.activity.last_finished_at == float("-inf")


class TestRequestContextCorrelation:
    @pytest.mark.anyio
    async def test_gate_event_carries_request_id(self, caplog) -> None:
        # Regression test for the registration order: the gate is added first so
        # it sits *inside* RequestTimingMiddleware, which means the request
        # context is already established and the wait can be correlated with the
        # request summary that includes it in duration_ms.
        clock = FakeClock()
        app = FastAPI()

        @app.get("/api/v1/things")
        async def things():
            return {"ok": True}

        app.add_middleware(
            BatchYieldMiddleware,
            quiet_s=1.5,
            max_wait_s=5.0,
            clock=clock,
            sleep=clock.sleep,
        )
        app.add_middleware(RequestTimingMiddleware)

        with caplog.at_level(logging.INFO, logger=_GATE_LOGGER):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                # Prime the window so the batch request actually waits and logs.
                await ac.get("/api/v1/things")
                response = await ac.get("/api/v1/things", headers=_BATCH_HEADERS)

        events = _gate_events(caplog)
        assert len(events) == 1
        assert events[0]["request_id"] == response.headers["X-Request-ID"]
        assert events[0]["route"] == "/api/v1/things"


class TestRegistration:
    def _classes(self, app: FastAPI) -> list[type]:
        return [m.cls for m in app.user_middleware]

    def test_gate_not_registered_by_default(self) -> None:
        app = create_app(Settings(), tracer_provider=None)
        assert BatchYieldMiddleware not in self._classes(app)

    def test_gate_is_innermost_user_middleware_when_enabled(self) -> None:
        app = create_app(
            Settings(environment="dev", batch_yield_enabled=True),
            tracer_provider=None,
        )
        # user_middleware[0] is outermost; the gate must be last (innermost) so a
        # deferred request resolves no dependencies, while the timing middleware
        # still measures the wait.
        assert self._classes(app) == [
            RequestTimingMiddleware,
            CORSMiddleware,
            BatchYieldMiddleware,
        ]

    def test_registration_converts_ms_settings_to_seconds(self) -> None:
        app = create_app(
            Settings(
                environment="dev",
                batch_yield_enabled=True,
                batch_yield_quiet_ms=750.0,
                batch_yield_max_wait_ms=3000.0,
            ),
            tracer_provider=None,
        )
        assert app.user_middleware[-1].kwargs == {"quiet_s": 0.75, "max_wait_s": 3.0}

    def test_gate_not_registered_in_prod_and_warns(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="stitch.api.middleware"):
            app = create_app(
                Settings(environment="prod", batch_yield_enabled=True),
                tracer_provider=None,
            )

        assert BatchYieldMiddleware not in self._classes(app)
        assert any("BATCH_YIELD_ENABLED" in r.getMessage() for r in caplog.records)


class TestSettings:
    def test_defaults_are_off_and_modest(self) -> None:
        settings = Settings()
        assert settings.batch_yield_enabled is False
        assert settings.batch_yield_quiet_ms == 1500.0
        assert settings.batch_yield_max_wait_ms == 5000.0

    def test_max_wait_is_bounded(self) -> None:
        # A fat-fingered max wait surfaces as a confusing client-side timeout in
        # a different service, so it is rejected at startup instead.
        with pytest.raises(ValueError):
            Settings(batch_yield_max_wait_ms=60_000.0)

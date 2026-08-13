"""Cooperative admission control: batch traffic yields to interactive traffic.

Entity-linkage calls the same public API surface as the frontend. That is a good
programming model, but it means a linkage run can crowd humans off a shared dev
server. It does so through *duty cycle*, not parallelism: the bulk pass is
strictly sequential (one request in flight at a time) yet issues a continuous
stream of the most expensive query in the system with no think time.

So this is not a concurrency limiter — a semaphore sized anywhere above 1 would
never engage. It is a rate control: a request that tags itself
``X-Stitch-Traffic-Class: batch`` waits while interactive requests are in flight
or have finished recently, and proceeds once the server has been quiet.

Three properties worth keeping in mind when changing this:

* **Untagged means interactive.** Only an explicit tag downgrades a caller, so
  there is nothing worth spoofing — the worst a client can do is decline to
  volunteer, which is a cooperative-system property rather than a security hole.
* **Classification needs no auth.** It reads one header, so a deferred request
  never pays the per-request RSA verify or the DB session checkout that
  dependency resolution triggers. This is why the gate must stay outside routing.
* **It never sheds.** After ``max_wait`` the request is admitted anyway, so this
  cannot fail a caller that knows nothing about it.

Dev/shared-server feature: inert unless ``batch_yield_enabled`` is set, and never
registered in prod — see :func:`stitch.api.middleware.register_middlewares`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import monotonic

from starlette.types import ASGIApp, Receive, Scope, Send
from stitch.observability.middleware import request_id_var, route_var

logger = logging.getLogger("stitch.api.admission")

# Namespaced ``X-Stitch-*`` like the other headers we invent (see
# stitch.observability.middleware). Owned here: this module is the authority for
# the wire contract, and entity-linkage sets the literal on its side.
TRAFFIC_CLASS_HEADER = "X-Stitch-Traffic-Class"
BATCH_TRAFFIC_CLASS = "batch"

_TRAFFIC_CLASS_HEADER_KEY = TRAFFIC_CLASS_HEADER.lower().encode("latin-1")

# Readiness must never depend on load. The docker healthcheck polls this every
# 5s, and entity-linkage's own startup probe uses a 2s timeout — a deferral here
# would flap the container unhealthy and convince EL the API is down.
#
# Matched against the raw ``scope["path"]``, which is the full path today because
# nothing fronts the API with prefix stripping and uvicorn runs without
# ``--root-path``. Revisit if either changes.
_HEALTH_PATH = "/api/v1/health"

# How precisely a waiting request notices the quiet window clear. Deliberately
# not a setting: it is not a delay we impose (the quiet check runs *before* the
# first sleep, so an idle server adds zero latency), and exposing it invites
# reading it as one. Must stay well below ``quiet_s`` or it dominates the
# resume time as overshoot.
_POLL_INTERVAL_S = 0.05


class InteractiveActivity:
    """In-flight count plus last-finish time for interactive requests.

    Both signals are needed. The counter alone misses active browsing, because
    interactive requests last tens of milliseconds and a poller would usually
    observe zero between them. The timestamp alone misses a *slow* interactive
    request that is still running, since nothing has finished yet and the window
    would read quiet.

    One event loop per worker, so plain attribute updates need no lock: every
    mutation happens between awaits and cannot be interleaved. That also makes
    this a per-process view — correct for the single-worker deployment, and only
    a partial view under ``--workers N`` (each worker would see its own share of
    interactive traffic and release batch traffic too eagerly).
    """

    __slots__ = ("in_flight", "last_finished_at")

    def __init__(self) -> None:
        self.in_flight = 0
        # -inf rather than 0.0: monotonic()'s epoch is arbitrary, so "never seen
        # an interactive request" has to read as "infinitely long ago".
        self.last_finished_at = float("-inf")

    def is_quiet(self, quiet_s: float, now: float) -> bool:
        return self.in_flight == 0 and (now - self.last_finished_at) >= quiet_s


def _is_batch(scope: Scope) -> bool:
    for key, value in scope["headers"]:
        if key == _TRAFFIC_CLASS_HEADER_KEY:
            decoded = value.decode("latin-1", "replace").strip().lower()
            return decoded == BATCH_TRAFFIC_CLASS
    return False


def _is_exempt(path: str) -> bool:
    # Only health. CORS preflights need no special case: CORSMiddleware is
    # registered outside this gate and answers a genuine preflight itself without
    # calling the inner app, so one never reaches here.
    return path == _HEALTH_PATH or path.startswith(_HEALTH_PATH + "/")


class BatchYieldMiddleware:
    """Hold batch-tagged requests while interactive traffic is active.

    Pure ASGI rather than ``BaseHTTPMiddleware``, for correctness rather than
    style: ``BaseHTTPMiddleware.call_next`` returns as soon as response *headers*
    are ready, so releasing the in-flight count after it would let batch traffic
    through while an interactive response was still streaming. ``await
    self.app(...)`` returns only once the response has been fully sent, which is
    the definition of "in flight" this gate needs. It also avoids adding a task
    group and two memory object streams to every *interactive* request — the
    traffic this exists to speed up.

    ``clock`` and ``sleep`` are injectable so tests can drive the quiet window
    deterministically instead of waiting on the wall clock.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        quiet_s: float,
        max_wait_s: float,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.app = app
        self.activity = InteractiveActivity()
        self._quiet_s = quiet_s
        self._max_wait_s = max_wait_s
        self._clock = clock
        self._sleep = sleep

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Exempt paths skip the accounting as well as the wait. Counting the
        # every-5s healthcheck as interactive activity would mean any
        # ``quiet_ms`` above ~5000 starves batch traffic forever with no human
        # load at all — a value that reads as conservative would silently mean
        # "never run".
        if scope["type"] != "http" or _is_exempt(scope["path"]):
            await self.app(scope, receive, send)
            return

        if _is_batch(scope):
            await self._wait_for_quiet()
            await self.app(scope, receive, send)
            return

        self.activity.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            # finally, not a trailing statement: a handler exception, a 500, or a
            # client disconnect (CancelledError) must all release the count. A
            # leak here wedges the gate shut for the life of the process and
            # makes every batch request pay the full max_wait.
            self.activity.in_flight -= 1
            self.activity.last_finished_at = self._clock()

    async def _wait_for_quiet(self) -> None:
        """Block until the server has been quiet, or ``max_wait_s`` elapses.

        Checks before sleeping, so a batch request arriving at an idle server is
        admitted with no added latency.
        """
        start = self._clock()
        deadline = start + self._max_wait_s
        slept = False

        while True:
            now = self._clock()
            if self.activity.is_quiet(self._quiet_s, now):
                if slept:
                    self._log_wait(now - start, "interactive_idle", logging.INFO)
                return

            remaining = deadline - now
            if remaining <= 0:
                self._log_wait(now - start, "max_wait_exceeded", logging.WARNING)
                return

            await self._sleep(min(_POLL_INTERVAL_S, remaining))
            slept = True

    def _log_wait(self, waited_s: float, outcome: str, level: int) -> None:
        # Read from the request context established by RequestTimingMiddleware,
        # which is registered outside this gate — so the wait can be correlated
        # with the request-summary event that includes it in duration_ms.
        logger.log(
            level,
            "batch_yield_wait",
            extra={
                "event": {
                    "request_id": request_id_var.get(),
                    "route": route_var.get(),
                    "gate_wait_ms": round(waited_s * 1000.0, 2),
                    "outcome": outcome,
                }
            },
        )

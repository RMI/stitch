from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class UniquenessPolicy(Protocol):
    """Decides whether two requests are "the same" job.

    ``key(params)`` returns a stable string for params that should collapse to a
    single shared run, or ``None`` to opt that request out of deduplication
    entirely (always start a fresh job).
    """

    def key(self, params: BaseModel) -> str | None:
        """Return the dedup key for ``params``, or ``None`` to skip dedup."""


class SingletonPolicy:
    """One job at a time, regardless of params.

    Every request maps to the same key, so while a run is active (or recently
    completed, within the manager's window) a second caller joins it instead of
    starting another. Use for services that must never run two jobs at once.
    """

    def __init__(self, key: str = "singleton") -> None:
        self._key = key

    def key(self, params: BaseModel) -> str | None:
        # params intentionally unused: every request maps to the same key.
        return self._key


class FingerprintPolicy:
    """Deduplicate by a hash of (a subset of) the request params.

    By default every field participates, so only byte-identical requests
    collapse. Narrow the key with ``include`` (allowlist) or widen what counts
    as "the same" with ``exclude`` (drop noisy/irrelevant fields). For example a
    GEM ETL can ``exclude={"payload_limit"}`` so a run capped at 500 and one
    capped at 501 are treated as the same job.
    """

    def __init__(
        self,
        *,
        include: Iterable[str] | None = None,
        exclude: Iterable[str] = (),
    ) -> None:
        self._include = set(include) if include is not None else None
        self._exclude = set(exclude)

    def key(self, params: BaseModel) -> str | None:
        data = params.model_dump(mode="json")
        if self._include is not None:
            data = {k: v for k, v in data.items() if k in self._include}
        if self._exclude:
            data = {k: v for k, v in data.items() if k not in self._exclude}
        blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return f"{type(params).__name__}:{digest}"


class CallablePolicy:
    """Adapt an arbitrary ``params -> key`` function into a policy."""

    def __init__(self, fn: Callable[[BaseModel], str | None]) -> None:
        self._fn = fn

    def key(self, params: BaseModel) -> str | None:
        return self._fn(params)


class NoDedupPolicy:
    """Never deduplicate: every request starts a new job."""

    def key(self, params: BaseModel) -> str | None:
        # params intentionally unused: opt every request out of dedup.
        return None

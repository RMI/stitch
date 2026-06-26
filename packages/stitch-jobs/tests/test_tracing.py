from __future__ import annotations

import asyncio

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic import BaseModel

from stitch.jobs import JobManager, SingletonPolicy
from stitch.jobs import manager as manager_module


class Params(BaseModel):
    name: str


class Result(BaseModel):
    value: int


@pytest.fixture
def tracing(monkeypatch) -> tuple[TracerProvider, InMemorySpanExporter]:
    """Local provider + in-memory exporter, with the manager's module-level
    tracer pointed at it for the duration of the test.

    Monkeypatching ``manager._tracer`` (rather than calling
    ``trace.set_tracer_provider``) keeps the process-global provider untouched —
    OTel makes the global set-once, so it can't be restored in teardown — so the
    suite stays isolated and order-independent.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(manager_module, "_tracer", provider.get_tracer("stitch.jobs"))
    return provider, exporter


async def _wait_terminal(manager: JobManager, job_id: str, *, timeout=2.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        record = await manager.get(job_id)
        if record is not None and record.is_terminal:
            return record
        await asyncio.sleep(0.005)
    raise AssertionError("job did not finish in time")


@pytest.mark.anyio
async def test_job_run_emits_root_span_linked_to_trigger(tracing) -> None:
    provider, exporter = tracing

    async def run(params: Params) -> Result:
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(run, policy=SingletonPolicy())

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("trigger") as trigger:
        trigger_ctx = trigger.get_span_context()
        record, _ = await manager.start(Params(name="a"))
    await _wait_terminal(manager, record.job_id)

    job_spans = [s for s in exporter.get_finished_spans() if s.name == "job.run"]
    assert len(job_spans) == 1
    job_span = job_spans[0]
    assert job_span.attributes["stitch.job.id"] == record.job_id
    assert job_span.attributes["stitch.job.state"] == "succeeded"
    # New root (not a child of the trigger), but linked back to it.
    assert job_span.parent is None
    assert any(link.context.span_id == trigger_ctx.span_id for link in job_span.links)


@pytest.mark.anyio
async def test_failed_job_span_has_error_status(tracing) -> None:
    _provider, exporter = tracing

    async def run(params: Params) -> Result:
        raise RuntimeError("boom")

    manager: JobManager[Params, Result] = JobManager(run, policy=SingletonPolicy())
    record, _ = await manager.start(Params(name="a"))
    await _wait_terminal(manager, record.job_id)

    job_span = next(s for s in exporter.get_finished_spans() if s.name == "job.run")
    assert job_span.status.status_code.name == "ERROR"
    assert job_span.attributes["stitch.job.state"] == "failed"

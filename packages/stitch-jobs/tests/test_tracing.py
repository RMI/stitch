from __future__ import annotations

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic import BaseModel

from stitch.jobs import JobManager, SingletonPolicy


class Params(BaseModel):
    name: str


class Result(BaseModel):
    value: int


# Sets the process-global provider once (the manager's module-level tracer is a
# proxy that resolves to it). This file sorts last in the package, so the
# earlier suites run with the default no-op tracer, unaffected.
@pytest.fixture(scope="module")
def span_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


@pytest.fixture
def spans(span_exporter: InMemorySpanExporter) -> InMemorySpanExporter:
    span_exporter.clear()
    return span_exporter


async def _wait_terminal(manager: JobManager, job_id: str, *, timeout=2.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        record = await manager.get(job_id)
        if record is not None and record.is_terminal:
            return record
        await asyncio.sleep(0.005)
    raise AssertionError("job did not finish in time")


@pytest.mark.anyio
async def test_job_run_emits_root_span_linked_to_trigger(spans) -> None:
    async def run(params: Params) -> Result:
        return Result(value=1)

    manager: JobManager[Params, Result] = JobManager(run, policy=SingletonPolicy())

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("trigger") as trigger:
        trigger_ctx = trigger.get_span_context()
        record, _ = await manager.start(Params(name="a"))
    await _wait_terminal(manager, record.job_id)

    job_spans = [s for s in spans.get_finished_spans() if s.name == "job.run"]
    assert len(job_spans) == 1
    job_span = job_spans[0]
    assert job_span.attributes["stitch.job.id"] == record.job_id
    assert job_span.attributes["stitch.job.state"] == "succeeded"
    # New root (not a child of the trigger), but linked back to it.
    assert job_span.parent is None
    assert any(link.context.span_id == trigger_ctx.span_id for link in job_span.links)


@pytest.mark.anyio
async def test_failed_job_span_has_error_status(spans) -> None:
    async def run(params: Params) -> Result:
        raise RuntimeError("boom")

    manager: JobManager[Params, Result] = JobManager(run, policy=SingletonPolicy())
    record, _ = await manager.start(Params(name="a"))
    await _wait_terminal(manager, record.job_id)

    job_span = next(s for s in spans.get_finished_spans() if s.name == "job.run")
    assert job_span.status.status_code.name == "ERROR"
    assert job_span.attributes["stitch.job.state"] == "failed"

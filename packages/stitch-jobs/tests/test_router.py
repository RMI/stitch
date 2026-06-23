from __future__ import annotations

import asyncio
import time

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.status import HTTP_403_FORBIDDEN

from stitch.jobs import FingerprintPolicy, JobManager, SingletonPolicy, make_job_router


class StartRequest(BaseModel):
    name: str


class Result(BaseModel):
    value: int


def _poll(client: TestClient, job_id: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/status/{job_id}").json()
        if body["state"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def build_app(manager: JobManager, **kwargs) -> FastAPI:
    app = FastAPI()
    router = make_job_router(
        manager,
        params_model=StartRequest,
        result_model=Result,
        **kwargs,
    )
    app.include_router(router, prefix="/api/v1")
    return app


def test_start_returns_202_and_status_succeeds() -> None:
    async def run(params: StartRequest) -> Result:
        return Result(value=len(params.name))

    app = build_app(
        JobManager(run, policy=SingletonPolicy()), initiated_by=lambda: "Tester"
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/start", json={"name": "alpha"})
        assert response.status_code == 202
        body = response.json()
        assert body["state"] == "running"
        assert body["initiated_by"] == "Tester"

        final = _poll(client, body["job_id"])
        assert final["state"] == "succeeded"
        assert final["result"] == {"value": 5}
        assert final["params"] == {"name": "alpha"}


def test_second_caller_joins_existing_run_with_200() -> None:
    async def slow_run(params: StartRequest) -> Result:
        await asyncio.sleep(0.3)
        return Result(value=1)

    app = build_app(JobManager(slow_run, policy=SingletonPolicy()))

    with TestClient(app) as client:
        first = client.post("/api/v1/start", json={"name": "a"})
        assert first.status_code == 202

        # Different user/params, singleton policy → joins the active run (200).
        second = client.post("/api/v1/start", json={"name": "b"})
        assert second.status_code == 200
        assert second.json()["job_id"] == first.json()["job_id"]

        _poll(client, first.json()["job_id"])


def test_fingerprint_policy_allows_distinct_jobs() -> None:
    async def slow_run(params: StartRequest) -> Result:
        await asyncio.sleep(0.3)
        return Result(value=1)

    app = build_app(JobManager(slow_run, policy=FingerprintPolicy()))

    with TestClient(app) as client:
        a = client.post("/api/v1/start", json={"name": "a"})
        b = client.post("/api/v1/start", json={"name": "b"})
        assert a.status_code == 202 and b.status_code == 202
        assert a.json()["job_id"] != b.json()["job_id"]

        _poll(client, a.json()["job_id"])
        _poll(client, b.json()["job_id"])


def test_status_404_for_unknown_job() -> None:
    async def run(params: StartRequest) -> Result:
        return Result(value=1)

    app = build_app(JobManager(run))
    with TestClient(app) as client:
        assert client.get("/api/v1/status/does-not-exist").status_code == 404


def test_jobs_listing_returns_recent_runs() -> None:
    async def run(params: StartRequest) -> Result:
        return Result(value=1)

    app = build_app(JobManager(run, policy=FingerprintPolicy()))

    with TestClient(app) as client:
        first = client.post("/api/v1/start", json={"name": "a"})
        _poll(client, first.json()["job_id"])
        second = client.post("/api/v1/start", json={"name": "b"})
        _poll(client, second.json()["job_id"])

        listed = client.get("/api/v1/jobs").json()
        assert {job["params"]["name"] for job in listed} == {"a", "b"}


def test_synthesized_force_field_bypasses_dedup() -> None:
    async def run(params: StartRequest) -> Result:
        return Result(value=1)

    # No force_attr wiring — make_job_router adds the `force` field itself.
    app = build_app(JobManager(run, policy=FingerprintPolicy(), recent_within=None))

    with TestClient(app) as client:
        first = client.post("/api/v1/start", json={"name": "a"})
        _poll(client, first.json()["job_id"])

        # Same params, no force → reuses the prior run.
        reused = client.post("/api/v1/start", json={"name": "a"})
        assert reused.status_code == 200
        assert reused.json()["job_id"] == first.json()["job_id"]

        # force=true → a fresh run, and `force` never lands in the dedup params.
        forced = client.post("/api/v1/start", json={"name": "a", "force": True})
        assert forced.status_code == 202
        assert forced.json()["job_id"] != first.json()["job_id"]
        assert forced.json()["params"] == {"name": "a"}
        _poll(client, forced.json()["job_id"])


def test_find_returns_runs_matching_params() -> None:
    async def run(params: StartRequest) -> Result:
        return Result(value=len(params.name))

    app = build_app(JobManager(run, policy=FingerprintPolicy(), recent_within=None))

    with TestClient(app) as client:
        a = client.post("/api/v1/start", json={"name": "a"})
        _poll(client, a.json()["job_id"])
        b = client.post("/api/v1/start", json={"name": "b"})
        _poll(client, b.json()["job_id"])

        found = client.post("/api/v1/find", json={"name": "a"}).json()
        assert [r["params"]["name"] for r in found] == ["a"]


def test_dependencies_gate_start() -> None:
    async def run(params: StartRequest) -> Result:
        return Result(value=1)

    def forbid() -> None:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="nope")

    app = build_app(JobManager(run), dependencies=[Depends(forbid)])
    with TestClient(app) as client:
        assert client.post("/api/v1/start", json={"name": "a"}).status_code == 403

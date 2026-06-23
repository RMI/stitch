import { describe, it, expect, vi, beforeEach } from "vitest";
import { findJobs, getJobStatus, listJobs, startJob } from "./jobs";

const BASE = "http://localhost:8002/api/v1/oil-gas-fields";

describe("job client", () => {
  let fetcher;

  beforeEach(() => {
    fetcher = vi.fn();
  });

  it("startJob POSTs the body to /start", async () => {
    fetcher.mockResolvedValueOnce({
      ok: true,
      status: 202,
      json: async () => ({ job_id: "job-1", state: "running" }),
    });

    const record = await startJob(
      BASE,
      { resource_id: 42, field: "basin", force: true },
      fetcher,
    );

    expect(fetcher).toHaveBeenCalledWith(`${BASE}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resource_id: 42, field: "basin", force: true }),
    });
    expect(record.job_id).toBe("job-1");
  });

  it("startJob surfaces structured detail and status on failure", async () => {
    fetcher.mockResolvedValueOnce({
      ok: false,
      status: 403,
      text: async () => JSON.stringify({ detail: "missing permission" }),
    });

    await expect(
      startJob(BASE, { resource_id: 42, field: "basin" }, fetcher),
    ).rejects.toMatchObject({ message: "missing permission", status: 403 });
  });

  it("getJobStatus GETs /status/{job_id}", async () => {
    fetcher.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ job_id: "job-1", state: "succeeded", result: {} }),
    });

    const record = await getJobStatus(BASE, "job-1", fetcher);

    expect(fetcher).toHaveBeenCalledWith(`${BASE}/status/job-1`, {
      method: "GET",
    });
    expect(record.state).toBe("succeeded");
  });

  it("listJobs GETs /jobs with a limit", async () => {
    fetcher.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [{ job_id: "job-1" }],
    });

    const records = await listJobs(BASE, fetcher, { limit: 10 });

    expect(fetcher).toHaveBeenCalledWith(`${BASE}/jobs?limit=10`, {
      method: "GET",
    });
    expect(records).toHaveLength(1);
  });

  it("findJobs POSTs the lookup params to /find", async () => {
    fetcher.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [{ job_id: "job-1", state: "succeeded" }],
    });

    const records = await findJobs(
      BASE,
      { resource_id: 42, field: "basin" },
      fetcher,
    );

    expect(fetcher).toHaveBeenCalledWith(`${BASE}/find`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resource_id: 42, field: "basin" }),
    });
    expect(records).toHaveLength(1);
  });
});

// Generic client for any Stitch job service. Every job-shaped service exposes
// the same routes under its base URL (POST /start, GET /status/{job_id},
// GET /jobs), so one client serves LLM, entity-linkage, and ETL alike.
//
// `baseUrl` is the URL where /start lives — e.g. the LLM suggestion jobs are at
// `${stitchLlmBaseUrl}/oil-gas-fields`, entity-linkage jobs at
// `${entityLinkageBaseUrl}`.

import { getErrorDetail } from "./api";

// Build an Error from a failed response, reusing the shared detail parser so
// job and CRUD paths surface identical messages.
async function errorFromResponse(response) {
  const error = new Error(await getErrorDetail(response));
  error.status = response.status;
  return error;
}

export async function startJob(baseUrl, body, fetcher) {
  const response = await fetcher(`${baseUrl}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await errorFromResponse(response);
  return await response.json();
}

export async function getJobStatus(baseUrl, jobId, fetcher) {
  const response = await fetcher(`${baseUrl}/status/${jobId}`, {
    method: "GET",
  });
  if (!response.ok) throw await errorFromResponse(response);
  return await response.json();
}

export async function listJobs(baseUrl, fetcher, { limit = 50 } = {}) {
  const response = await fetcher(`${baseUrl}/jobs?limit=${limit}`, {
    method: "GET",
  });
  if (!response.ok) throw await errorFromResponse(response);
  return await response.json();
}

// Return the runs matching a request's params (server applies the same dedup
// policy as /start), newest first. Lets the UI discover/reuse the existing run
// for exactly these params without fetching-then-filtering the whole job list.
export async function findJobs(baseUrl, body, fetcher) {
  const response = await fetcher(`${baseUrl}/find`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await errorFromResponse(response);
  return await response.json();
}

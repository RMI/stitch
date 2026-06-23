// Generic client for any Stitch job service. Every job-shaped service exposes
// the same routes under its base URL (POST /start, GET /status/{job_id},
// GET /jobs), so one client serves LLM, entity-linkage, and ETL alike.
//
// `baseUrl` is the URL where /start lives — e.g. the LLM suggestion jobs are at
// `${stitchLlmBaseUrl}/oil-gas-fields`, entity-linkage jobs at
// `${entityLinkageBaseUrl}`.

async function errorFromResponse(response) {
  let detail = response.statusText || `HTTP error! status: ${response.status}`;
  try {
    const text = await response.text();
    if (text) {
      try {
        const body = JSON.parse(text);
        const parsed = body?.detail;
        if (typeof parsed === "string" && parsed) {
          detail = parsed;
        } else if (parsed != null) {
          detail = JSON.stringify(parsed, null, 2);
        } else {
          detail = text;
        }
      } catch {
        detail = text;
      }
    }
  } catch {
    // fall back to statusText
  }
  const error = new Error(detail);
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

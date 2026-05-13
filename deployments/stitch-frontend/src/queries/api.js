export async function getResources(
  config,
  fetcher,
  endpoint = "resources",
  { page = 1, page_size = 50, filters = {}, sort_by, sort_order } = {},
) {
  const params = new URLSearchParams({ page, page_size });
  for (const [key, values] of Object.entries(filters)) {
    for (const v of values) {
      params.append(key, v);
    }
  }
  if (sort_by) params.set("sort_by", sort_by);
  if (sort_order) params.set("sort_order", sort_order);
  const url = `${config.apiBaseUrl}/${endpoint}/?${params}`;
  const response = await fetcher(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return await response.json();
}

export async function getResource(config, id, fetcher, endpoint = "resources") {
  const url = `${config.apiBaseUrl}/${endpoint}/${id}`;
  const response = await fetcher(url);
  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  const data = await response.json();
  return data;
}

export async function getResourceDetail(
  config,
  id,
  fetcher,
  endpoint = "resources",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/${id}/detail`;
  const response = await fetcher(url);
  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  const data = await response.json();
  return data;
}

export async function createLLMSuggestion(
  config,
  id,
  field,
  fetcher,
  endpoint = "resources",
) {
  const url = new URL(`${config.stitchLlmBaseUrl}/${endpoint}/${id}`);
  url.searchParams.set("field", field);
  const response = await fetcher(url, {
    method: "GET",
  });

  if (!response.ok) {
    let detail = `HTTP error! status: ${response.status}`;
    try {
      const payload = await response.json();
      if (payload?.detail) detail = payload.detail;
    } catch {
      // Ignore JSON parsing failures and fall back to status text.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

function formatApiErrorDetail(detail, fallbackStatus) {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) || (detail && typeof detail === "object")) {
    return JSON.stringify(detail, null, 2);
  }
  return `HTTP error! status: ${fallbackStatus}`;
}

export async function createResource(
  config,
  payload,
  fetcher,
  endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/`;
  const response = await fetcher(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = `HTTP error! status: ${response.status}`;
    try {
      const body = await response.json();
      detail = formatApiErrorDetail(body?.detail, response.status);
    } catch {
      // Ignore JSON parsing failures and fall back to status text.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

export async function createMergeCandidate(
  config,
  resource_ids,
  fetcher,
  endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/merge-candidates`;
  const response = await fetcher(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resource_ids }),
  });

  if (!response.ok) {
    let detail = `HTTP error! status: ${response.status}`;
    try {
      const body = await response.json();
      detail = formatApiErrorDetail(body?.detail, response.status);
    } catch {
      // Ignore JSON parsing failures and fall back to status text.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

export async function getMergeCandidates(
  config,
  fetcher,
  endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/merge-candidates`;
  const response = await fetcher(url);

  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

export async function getMergeCandidate(
  config,
  id,
  fetcher,
  endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/merge-candidates/${id}`;
  const response = await fetcher(url);

  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

export async function reviewMergeCandidate(
  config,
  id,
  action,
  fetcher,
  endpoint = "oil-gas-fields",
  review_notes = "",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/merge-candidates/${id}/${action}`;
  const response = await fetcher(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ review_notes }),
  });

  if (!response.ok) {
    const text = await response.text();
    let detail = text;

    try {
      detail = text ? JSON.parse(text) : null;
    } catch {
      // leave as text
    }

    const error = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail, null, 2),
    );
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

export async function getMergeCandidatePreview(
  config,
  id,
  fetcher,
  endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/merge-candidates/${id}/preview`;
  const response = await fetcher(url);

  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

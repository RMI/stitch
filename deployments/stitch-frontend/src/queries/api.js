export async function getResources(
  config,
  fetcher,
  endpoint = "resources",
  { page = 1, page_size = 50, filters = {}, q, sort_by, sort_order } = {},
) {
  const params = new URLSearchParams({ page, page_size });
  for (const [key, values] of Object.entries(filters)) {
    for (const v of values) {
      params.append(key, v);
    }
  }
  if (q) params.set("q", q);
  if (sort_by) params.set("sort_by", sort_by);
  if (sort_order) params.set("sort_order", sort_order);
  const url = `${config.apiBaseUrl}/${endpoint}/?${params}`;
  const response = await fetcher(url);
  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return await response.json();
}

export async function getResourceFilterOptions(
  config,
  fetcher,
  endpoint = "resources",
  field,
) {
  const params = new URLSearchParams({ field });
  const url = `${config.apiBaseUrl}/${endpoint}/filter-options?${params}`;
  const response = await fetcher(url);
  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
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

export async function getFieldSourceValues(
  config,
  id,
  field,
  fetcher,
  endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/${id}/fields/${encodeURIComponent(
    field,
  )}/sources`;
  const response = await fetcher(url);
  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return await response.json();
}

export async function updateFieldSourcePriority(
  config,
  id,
  field,
  orderedSourcePks,
  fetcher,
  endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/${id}/fields/${encodeURIComponent(
    field,
  )}/sources/priority`;
  const response = await fetcher(url, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ ordered_source_pks: orderedSourcePks }),
  });
  if (!response.ok) {
    const detail = await getErrorDetail(response);
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return await response.json();
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
    const detail = await getErrorDetail(response);
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

async function getErrorDetail(response) {
  const fallback = formatApiErrorDetail(null, response.status);

  try {
    const text = await response.text();
    if (!text) return response.statusText || fallback;

    try {
      const body = JSON.parse(text);
      return formatApiErrorDetail(body?.detail, response.status);
    } catch {
      return text;
    }
  } catch {
    return response.statusText || fallback;
  }
}

export async function createSourceForResource(
  config,
  resourceId,
  sourcePayload,
  fetcher,
  endpoint = "oil-gas-fields",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/${resourceId}/sources`;
  const response = await fetcher(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sourcePayload),
  });

  if (!response.ok) {
    const detail = await getErrorDetail(response);
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
    const detail = await getErrorDetail(response);
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

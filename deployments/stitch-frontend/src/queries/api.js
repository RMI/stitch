import config from "../config/env";

export async function getResources(
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

export async function getResource(id, fetcher, endpoint = "resources") {
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

export async function getResourceDetail(id, fetcher, endpoint = "resources") {
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
  id,
  field,
  fetcher,
  endpoint = "resources",
) {
  const url = `${config.apiBaseUrl}/${endpoint}/${id}/llm-suggestions`;
  const response = await fetcher(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ field }),
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

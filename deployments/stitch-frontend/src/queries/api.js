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

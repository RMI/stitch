const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

async function authedFetch(url, getAccessTokenSilently, options = {}) {
  const token = await getAccessTokenSilently();
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const err = new Error(`HTTP error! status: ${response.status}`);
    err.status = response.status;
    err.body = await response.text().catch(() => "");
    throw err;
  }
  return response.json();
}

export function getResources(getAccessTokenSilently) {
  const url = `${API_BASE_URL}/resources/`;
  return authedFetch(url, getAccessTokenSilently);
}

export function getResource(id, getAccessTokenSilently) {
  const url = `${API_BASE_URL}/resources/${id}`;
  return authedFetch(url, getAccessTokenSilently);
}

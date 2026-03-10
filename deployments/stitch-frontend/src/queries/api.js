import config from "../config/env";

export async function getResources(fetcher) {
  const url = `${config.apiBaseUrl}/resources/`;
  const response = await fetcher(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  const data = await response.json();
  return data;
}

export async function getResource(id, fetcher) {
  const url = `${config.apiBaseUrl}/resources/${id}`;
  const response = await fetcher(url);
  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  const data = await response.json();
  return data;
}

export async function getOGFields(fetcher) {
  const url = `${config.apiBaseUrl}/oil-gas-fields/`;
  const response = await fetcher(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  const data = await response.json();
  return data;
}

export async function getOGField(id, fetcher) {
  const url = `${config.apiBaseUrl}/oil-gas-fields/${id}`;
  const response = await fetcher(url);
  if (!response.ok) {
    const error = new Error(`HTTP error! status: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  const data = await response.json();
  return data;
}

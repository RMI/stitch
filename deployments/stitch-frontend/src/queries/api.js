const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export async function getResources() {
  const url = `${API_BASE_URL}/api/v1/resources/`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  const data = await response.json();
  return data;
}

export async function getResource(id) {
  const url = `${API_BASE_URL}/api/v1/resources/${id}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  const data = await response.json();
  return data;
}

const base = window.__safa_HAWA__?.apiBaseUrl ?? "/api/v1";

async function get(path) {
  const response = await fetch(`${base}${path}`);
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`${response.status} ${response.statusText} — ${detail.slice(0, 120)}`);
  }
  return response.json();
}

export const api = {
  stations: () => get("/stations"),
  latest: () => get("/latest"),
  worst: () => get("/worst"),
  readings: (slug, hours) => get(`/stations/${slug}/readings?hours=${hours}`),
  summary: (slug, days) => get(`/stations/${slug}/summary?days=${days}`),
  ingestStatus: () => get("/ingest/status"),
};

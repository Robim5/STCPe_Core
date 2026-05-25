export function buildDisplayPath(endpoint, params) {
  let path = endpoint.path;
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    const trimmed = String(value ?? "").trim();
    if (!trimmed) return;
    const token = `{${key}}`;
    if (path.includes(token)) {
      path = path.replace(token, trimmed);
    } else {
      query.set(key, trimmed);
    }
  });

  const qs = query.toString();
  return `${endpoint.metodo} ${path}${qs ? `?${qs}` : ""}`;
}

export function buildRequest(endpoint, params, baseUrl) {
  let path = endpoint.path;
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    const trimmed = String(value ?? "").trim();
    if (!trimmed) return;
    const token = `{${key}}`;
    if (path.includes(token)) {
      path = path.replace(token, encodeURIComponent(trimmed));
    } else {
      query.set(key, trimmed);
    }
  });

  const normalizedBase = (baseUrl || "").trim().replace(/\/+$/, "");
  const full = `${normalizedBase}${path}${query.toString() ? `?${query.toString()}` : ""}`;
  return { full, displayPath: buildDisplayPath(endpoint, params) };
}

export async function runHttpRequest(method, fullUrl, apiKey) {
  const headers = {};
  if ((apiKey || "").trim()) headers["X-API-Key"] = apiKey.trim();

  const startedAt = Date.now();
  const response = await fetch(fullUrl, { method, headers });
  const text = await response.text();
  const elapsedMs = Date.now() - startedAt;
  return { response, text, elapsedMs };
}

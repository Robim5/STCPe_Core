const KEY = "stcpe_connect_v1";

export function loadConnect() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveConnect(baseUrl, apiKey) {
  localStorage.setItem(KEY, JSON.stringify({ baseUrl, apiKey }));
}

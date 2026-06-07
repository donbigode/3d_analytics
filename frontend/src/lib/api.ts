const BASE = "/api"; // proxy in dev; same-origin in prod when backend serves the build

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, { ...init, credentials: "include" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

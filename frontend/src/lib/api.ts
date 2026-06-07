const BASE = "/api"; // proxy in dev; same-origin in prod when backend serves the build

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `API ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, { ...init, credentials: "include" });
  if (!res.ok) {
    let detail: unknown = null;
    const text = await res.text().catch(() => "");
    if (text) {
      try {
        detail = JSON.parse(text);
      } catch {
        detail = text;
      }
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  if (!ct.includes("application/json")) return undefined as T;
  return (await res.json()) as T;
}

export function errorMessage(err: unknown, fallback = "Erro ao processar a requisição."): string {
  if (err instanceof ApiError) {
    const d = err.detail as { detail?: string | { msg?: string }[] } | null;
    if (typeof d?.detail === "string") return d.detail;
    if (Array.isArray(d?.detail) && d.detail[0]?.msg) return d.detail[0].msg as string;
    if (err.status === 401) return "Sessão expirada. Faça login novamente.";
    if (err.status === 409) return "Conflito: registro está em uso.";
    return `${fallback} (HTTP ${err.status})`;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

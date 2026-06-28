/** Tiny typed fetch wrapper with auth header + transparent refresh-token retry. */
const BASE = (import.meta as any).env?.VITE_API_URL ?? "";

const STORE = {
  get access() { return localStorage.getItem("an_access"); },
  set access(v: string | null) { v ? localStorage.setItem("an_access", v) : localStorage.removeItem("an_access"); },
  get refresh() { return localStorage.getItem("an_refresh"); },
  set refresh(v: string | null) { v ? localStorage.setItem("an_refresh", v) : localStorage.removeItem("an_refresh"); },
};

export const tokenStore = STORE;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function raw<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (STORE.access) headers["Authorization"] = `Bearer ${STORE.access}`;
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && retry && STORE.refresh && !path.includes("/auth/")) {
    const ok = await tryRefresh();
    if (ok) return raw<T>(method, path, body, false);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function tryRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: STORE.refresh }),
    });
    if (!res.ok) { STORE.access = null; STORE.refresh = null; return false; }
    const data = await res.json();
    STORE.access = data.access_token; STORE.refresh = data.refresh_token;
    return true;
  } catch { return false; }
}

export const api = {
  get: <T>(p: string) => raw<T>("GET", p),
  post: <T>(p: string, b?: unknown) => raw<T>("POST", p, b),
  put: <T>(p: string, b?: unknown) => raw<T>("PUT", p, b),
  del: <T>(p: string) => raw<T>("DELETE", p),
};

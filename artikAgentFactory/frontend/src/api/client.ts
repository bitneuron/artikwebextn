/** Tiny typed fetch wrapper. Session auth via httponly cookie — `credentials:
 * "include"` on every call so it's sent cross-port in dev (Vite :5173 -> API :8420)
 * and same-origin in production. A 401 clears the app's auth state and redirects to
 * login (registered from AuthContext via `setUnauthorizedHandler`, avoiding an
 * import cycle between this file and the context). */
const BASE = (import.meta as any).env?.VITE_API_URL ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

const AUTH_EXEMPT_PATHS = ["/api/auth/login", "/api/auth/me"];

async function raw<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && onUnauthorized && !AUTH_EXEMPT_PATHS.includes(path)) {
    onUnauthorized();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T,>(p: string) => raw<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => raw<T>("POST", p, b),
  put: <T,>(p: string, b?: unknown) => raw<T>("PUT", p, b),
  del: <T,>(p: string) => raw<T>("DELETE", p),
};

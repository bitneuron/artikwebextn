import { api } from "./client";

export type Role = "administrator" | "agent_manager" | "researcher" | "viewer";

export type CurrentUser = {
  id: number;
  email: string;
  username: string;
  full_name: string | null;
  role: Role;
  workspace_id: number;
  is_active: boolean;
  must_reset_password: boolean;
  created_at: string;
  last_login_at: string | null;
};

export const authApi = {
  login: (identifier: string, password: string) => api.post<CurrentUser>("/api/auth/login", { identifier, password }),
  logout: () => api.post<{ detail: string }>("/api/auth/logout"),
  me: () => api.get<CurrentUser>("/api/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    api.post<{ detail: string }>("/api/auth/change-password", { current_password, new_password }),
};

export const usersApi = {
  list: () => api.get<CurrentUser[]>("/api/users"),
  create: (body: { email: string; username: string; full_name?: string; password: string; role: Role }) =>
    api.post<CurrentUser>("/api/users", body),
  update: (id: number, body: Partial<{ full_name: string; role: Role; is_active: boolean }>) =>
    api.put<CurrentUser>(`/api/users/${id}`, body),
  forceReset: (id: number) => api.post<{ detail: string }>(`/api/users/${id}/force-reset`),
};

export type AuditEvent = {
  id: number;
  ts: string;
  actor_user_id: number | null;
  actor_label: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: string;
  request_id: string | null;
  ip_address: string | null;
  metadata: Record<string, unknown>;
};

export const auditApi = {
  list: (params: { action?: string; resource_type?: string; outcome?: string } = {}) => {
    const parts = Object.entries(params).filter(([, v]) => v);
    const q = parts.length ? `?${new URLSearchParams(parts as [string, string][]).toString()}` : "";
    return api.get<AuditEvent[]>(`/api/audit-events${q}`);
  },
};

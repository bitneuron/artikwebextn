import { api } from "./client";
import { Agent, AgentDraft, AgentListItem, Dashboard, Run } from "./types";

export type AgentListParams = {
  status?: string;
  template_id?: string;
  search?: string;
  sort?: string;
  order?: string;
};

function qs(params: Record<string, string | undefined>): string {
  const parts = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  return parts.length ? `?${new URLSearchParams(parts as [string, string][]).toString()}` : "";
}

export const agentsApi = {
  list: (params: AgentListParams = {}) => api.get<AgentListItem[]>(`/api/agents${qs(params)}`),
  get: (id: number) => api.get<Agent>(`/api/agents/${id}`),
  create: (draft: AgentDraft) => api.post<Agent>("/api/agents", draft),
  update: (id: number, draft: Partial<AgentDraft>) => api.put<Agent>(`/api/agents/${id}`, draft),
  remove: (id: number) => api.del<{ detail: string }>(`/api/agents/${id}`),
  pause: (id: number) => api.post<Agent>(`/api/agents/${id}/pause`),
  resume: (id: number) => api.post<Agent>(`/api/agents/${id}/resume`),
  duplicate: (id: number) => api.post<Agent>(`/api/agents/${id}/duplicate`),
  run: (id: number) => api.post<Run>(`/api/agents/${id}/run`),
};

export const dashboardApi = {
  get: () => api.get<Dashboard>("/api/dashboard"),
};

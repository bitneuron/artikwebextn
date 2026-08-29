import { api } from "./client";
import { Run, RunLog } from "./types";

export const runsApi = {
  listForAgent: (agentId: number) => api.get<Run[]>(`/api/agents/${agentId}/runs`),
  listAll: (params: { status?: string; trigger?: string } = {}) => {
    const parts = Object.entries(params).filter(([, v]) => v);
    const q = parts.length ? `?${new URLSearchParams(parts as [string, string][]).toString()}` : "";
    return api.get<Run[]>(`/api/runs${q}`);
  },
  get: (id: number) => api.get<Run>(`/api/runs/${id}`),
  logs: (id: number) => api.get<RunLog[]>(`/api/runs/${id}/logs`),
};

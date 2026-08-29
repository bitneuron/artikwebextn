import { api } from "./client";
import { AlertEvent } from "./types";

export const alertsApi = {
  listForAgent: (agentId: number) => api.get<AlertEvent[]>(`/api/agents/${agentId}/alert-events`),
};

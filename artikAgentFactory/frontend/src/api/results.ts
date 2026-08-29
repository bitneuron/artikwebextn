import { api } from "./client";
import { Note, Result, ResultDetail } from "./types";

export type ResultListParams = {
  category?: string;
  change_status?: string;
  is_saved?: boolean;
  is_dismissed?: boolean;
  min_relevance?: number;
  search?: string;
  sort?: string;
  order?: string;
};

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  return parts.length ? `?${new URLSearchParams(parts as [string, string][]).toString()}` : "";
}

export type SourceSummary = { source_name: string | null; domain: string; count: number; credibility: string };

export const resultsApi = {
  list: (agentId: number, params: ResultListParams = {}) =>
    api.get<Result[]>(`/api/agents/${agentId}/results${qs(params as any)}`),
  sources: (agentId: number) => api.get<SourceSummary[]>(`/api/agents/${agentId}/sources`),
  get: (id: number) => api.get<ResultDetail>(`/api/results/${id}`),
  save: (id: number) => api.post<Result>(`/api/results/${id}/save`),
  unsave: (id: number) => api.post<Result>(`/api/results/${id}/unsave`),
  dismiss: (id: number) => api.post<Result>(`/api/results/${id}/dismiss`),
  undismiss: (id: number) => api.post<Result>(`/api/results/${id}/undismiss`),
  addNote: (id: number, body: string) => api.post<Note>(`/api/results/${id}/notes`, { body }),
  updateNote: (noteId: number, body: string) => api.put<Note>(`/api/notes/${noteId}`, { body }),
  deleteNote: (noteId: number) => api.del<{ detail: string }>(`/api/notes/${noteId}`),
};

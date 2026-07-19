// Thin API client for the ArtikResearch backend.
const J = { "Content-Type": "application/json" };

async function req(path: string, opts?: RequestInit) {
  const r = await fetch(path, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

export const api = {
  dashboard: () => req("/api/dashboard"),
  status: () => req("/api/status"),
  agents: () => req("/api/agents"),

  papers: () => req("/api/papers"),
  paper: (id: string) => req(`/api/papers/${id}`),
  uploadPaper: (form: FormData) => fetch("/api/papers", { method: "POST", body: form }).then(r => r.json()),
  readPaper: (id: string) => req(`/api/papers/${id}/read`, { method: "POST" }),
  deletePaper: (id: string) => req(`/api/papers/${id}`, { method: "DELETE" }),
  updateSettings: (id: string, s: { target_journal?: string; output_format?: string }) =>
    req(`/api/papers/${id}/settings`, { method: "PUT", headers: J, body: JSON.stringify(s) }),
  convert: (id: string, journal?: string, output_format?: string) =>
    req(`/api/papers/${id}/convert`, { method: "POST", headers: J, body: JSON.stringify({ journal, output_format }) }),
  exportUrl: (id: string, fmt: string) => `/api/papers/${id}/export?format=${encodeURIComponent(fmt)}`,

  journals: () => req("/api/journals"),
  journal: (name: string) => req(`/api/journals/${encodeURIComponent(name)}`),
  learnJournalText: (name: string, text: string) =>
    req(`/api/journals/${encodeURIComponent(name)}/learn-text`, { method: "POST", headers: J, body: JSON.stringify({ text }) }),
  uploadJournalDoc: (name: string, form: FormData) =>
    fetch(`/api/journals/${encodeURIComponent(name)}/upload`, { method: "POST", body: form }).then(r => r.json()),
  compareJournals: (journals: string[], paper_id?: string) =>
    req("/api/journals/compare", { method: "POST", headers: J, body: JSON.stringify({ journals, paper_id }) }),

  gaps: (id: string, journal?: string) => req(`/api/analysis/${id}/gaps`, { method: "POST", headers: J, body: JSON.stringify({ journal }) }),
  compliance: (id: string, journal?: string) => req(`/api/analysis/${id}/compliance`, { method: "POST", headers: J, body: JSON.stringify({ journal }) }),
  review: (id: string, journal?: string) => req(`/api/analysis/${id}/review`, { method: "POST", headers: J, body: JSON.stringify({ journal }) }),
  references: (id: string, style?: string) => req(`/api/analysis/${id}/references`, { method: "POST", headers: J, body: JSON.stringify({ style }) }),
  buildPackage: (id: string, journal?: string) => req(`/api/analysis/${id}/package`, { method: "POST", headers: J, body: JSON.stringify({ journal }) }),

  chatHistory: (id: string) => req(`/api/chat/${id}`),
  chat: (id: string, message: string) => req(`/api/chat/${id}`, { method: "POST", headers: J, body: JSON.stringify({ message }) }),
  manuscript: (id: string) => req(`/api/chat/${id}/manuscript`),
};

export type Paper = {
  id: string; name: string; fmt: string; target_journal?: string; output_format?: string; status: string;
  readiness?: number; summary?: string; knowledge?: any; created_at: string; updated_at: string;
};
export type Journal = { id?: string; name: string; source: string; profile: any; files: any[] };

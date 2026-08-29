import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { agentsApi, dashboardApi } from "../api/agents";
import { templatesApi } from "../api/templates";
import { AgentListItem, Dashboard as DashboardType, Template } from "../api/types";
import AgentCard from "../components/AgentCard";
import StatCard from "../components/StatCard";

export default function Dashboard() {
  const nav = useNavigate();
  const [agents, setAgents] = useState<AgentListItem[] | null>(null);
  const [templates, setTemplates] = useState<Record<string, Template>>({});
  const [dashboard, setDashboard] = useState<DashboardType | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [sort, setSort] = useState("updated_at");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const [a, t, d] = await Promise.all([agentsApi.list(), templatesApi.list(), dashboardApi.get()]);
      setAgents(a);
      setTemplates(Object.fromEntries(t.map((x) => [x.id, x])));
      setDashboard(d);
    } catch (e: any) {
      setError(e.message ?? "Failed to load dashboard");
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    if (!agents) return [];
    let rows = agents;
    if (statusFilter) rows = rows.filter((a) => a.status === statusFilter);
    if (typeFilter) rows = rows.filter((a) => a.template_id === typeFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter((a) => a.name.toLowerCase().includes(q) || (a.description ?? "").toLowerCase().includes(q));
    }
    const sorted = [...rows].sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
    return sorted;
  }, [agents, search, statusFilter, typeFilter, sort]);

  async function mutate(id: number, fn: (id: number) => Promise<unknown>) {
    await fn(id);
    load();
  }

  return (
    <div className="mx-auto max-w-7xl">
      <div className="relative mb-8 overflow-hidden rounded-3xl border border-border bg-surface p-6 md:p-8">
        <div className="pointer-events-none absolute inset-0 bg-grad-radial-hero" />
        <div className="relative flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <h1 className="font-display text-2xl font-extrabold tracking-tight text-ink md:text-3xl">Agents</h1>
            <p className="mt-1.5 max-w-xl text-sm text-ink-dim">
              Every research agent you've deployed, what they found, and when they run next.
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={() => nav("/runs")}>Run History</button>
            <button className="btn-primary" onClick={() => nav("/agents/new")}>+ Create Agent</button>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-sm text-bad">{error}</div>
      )}

      {dashboard && (
        <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard label="Total agents" value={dashboard.total_agents} accent="blue" />
          <StatCard label="Active" value={dashboard.active_agents} accent="ok" />
          <StatCard label="Paused" value={dashboard.paused_agents} accent="warn" />
          <StatCard label="New findings (7d)" value={dashboard.new_findings_7d} accent="violet" />
          <StatCard label="High priority" value={dashboard.high_priority_alerts} accent="bad" />
          <StatCard
            label="Scheduler"
            value={dashboard.scheduler_running ? "Online" : "Offline"}
            accent={dashboard.scheduler_running ? "ok" : "bad"}
          />
        </div>
      )}

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <input
          className="input max-w-xs"
          placeholder="Search agents…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search agents"
        />
        <select className="select w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="paused">Paused</option>
        </select>
        <select className="select w-auto" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Filter by type">
          <option value="">All types</option>
          {Object.values(templates).map((t) => (
            <option key={t.id} value={t.id}>{t.icon} {t.name}</option>
          ))}
        </select>
        <select className="select w-auto" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort agents">
          <option value="updated_at">Recent activity</option>
          <option value="name">Name</option>
        </select>
        <button className="btn-ghost ml-auto" onClick={load}>↻ Refresh</button>
      </div>

      {agents === null && !error && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton h-56 rounded-2xl" />
          ))}
        </div>
      )}

      {agents !== null && filtered.length === 0 && (
        <div className="card flex flex-col items-center gap-3 p-12 text-center">
          <div className="text-3xl">🛰️</div>
          <h3 className="font-display text-lg font-bold">No agents yet</h3>
          <p className="max-w-sm text-sm text-ink-dim">
            Create your first research agent from a template, describe what it should look into, and let it run in the background.
          </p>
          <button className="btn-primary mt-2" onClick={() => nav("/agents/new")}>+ Create Agent</button>
        </div>
      )}

      {agents !== null && filtered.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((a, i) => (
            <AgentCard
              key={a.id}
              agent={a}
              template={templates[a.template_id]}
              index={i}
              onRun={(id) => mutate(id, agentsApi.run)}
              onPause={(id) => mutate(id, agentsApi.pause)}
              onResume={(id) => mutate(id, agentsApi.resume)}
              onDuplicate={(id) => mutate(id, agentsApi.duplicate)}
              onDelete={(id) => mutate(id, agentsApi.remove)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

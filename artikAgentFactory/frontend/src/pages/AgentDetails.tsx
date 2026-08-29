import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { agentsApi } from "../api/agents";
import { resultsApi } from "../api/results";
import { templatesApi } from "../api/templates";
import { Agent, Result, Template } from "../api/types";
import { AgentStatusBadge } from "../components/StatusBadge";
import StatCard from "../components/StatCard";
import ConfirmDialog from "../components/ConfirmDialog";
import ResultsTab from "../components/ResultsTab";
import SourcesTab from "../components/SourcesTab";
import DeadlinesTab from "../components/DeadlinesTab";
import RunHistoryTable from "../components/RunHistoryTable";
import LogsPane from "../components/LogsPane";
import AlertEventsList from "../components/AlertEventsList";
import { relativeTime, scheduleSummary, titleCase } from "../lib/format";

const TAB_TO_CATEGORY: Record<string, string> = {
  schools: "school", programs: "program", opportunities: "opportunity", articles: "article",
};

const TAB_LABEL: Record<string, string> = {
  overview: "Overview", results: "Results", schools: "Schools", programs: "Programs",
  opportunities: "Opportunities", articles: "Articles", sources: "Sources",
  deadlines: "Deadlines", run_history: "Run History", logs: "Logs", settings: "Settings",
};

export default function AgentDetails() {
  const { id } = useParams();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [template, setTemplate] = useState<Template | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [running, setRunning] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [allResults, setAllResults] = useState<Result[] | null>(null);

  const tab = params.get("tab") || "overview";
  const agentId = Number(id);

  async function load() {
    const a = await agentsApi.get(agentId);
    setAgent(a);
    const t = await templatesApi.get(a.template_id);
    setTemplate(t);
    resultsApi.list(agentId, { is_dismissed: false }).then(setAllResults);
  }

  useEffect(() => {
    load();
  }, [id]);

  if (!agent || !template) {
    return <div className="mx-auto max-w-6xl"><div className="skeleton h-64 rounded-2xl" /></div>;
  }

  const tabs = template.detail_tabs;

  async function runNow() {
    setRunning(true);
    setRunMessage(null);
    try {
      const run = await agentsApi.run(agent!.id);
      setRunMessage(run.status === "completed" ? `Run complete — ${run.result_count_total} results.` : run.error_message ?? `Run ${run.status}.`);
      load();
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl">
      <button className="mb-4 text-sm text-ink-mute hover:text-ink" onClick={() => nav("/")}>← All agents</button>

      <div className="card relative overflow-hidden p-6">
        <div className="pointer-events-none absolute inset-0 bg-grad-radial-hero" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-surface-2 text-2xl">{template.icon}</div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="font-display text-xl font-extrabold text-ink">{agent.name}</h1>
                <AgentStatusBadge status={agent.status} />
              </div>
              <div className="mt-1 text-xs text-ink-mute">
                {template.name} · {scheduleSummary(agent.schedule)} · last run {relativeTime(agent.last_run_at)}
              </div>
              {agent.description && <p className="mt-2 max-w-xl text-sm text-ink-dim">{agent.description}</p>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary btn-sm" disabled={running} onClick={runNow}>
              {running ? "Running…" : "▶ Run Now"}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => nav(`/agents/${agent.id}/edit`)}>Edit</button>
            <button
              className="btn-ghost btn-sm"
              onClick={async () => { await (agent.status === "active" ? agentsApi.pause : agentsApi.resume)(agent.id); load(); }}
            >
              {agent.status === "active" ? "Pause" : "Resume"}
            </button>
            <button className="btn-danger btn-sm" onClick={() => setConfirmDelete(true)}>Delete</button>
          </div>
        </div>
      </div>

      {runMessage && (
        <div className="mt-4 rounded-xl border border-blue/30 bg-blue/10 px-4 py-3 text-sm text-ink">{runMessage}</div>
      )}

      <div className="my-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Total results" value={allResults?.length ?? "…"} accent="blue" />
        <StatCard label="New" value={allResults?.filter((r) => r.change_status === "new").length ?? "…"} accent="ok" />
        <StatCard label="Changed" value={allResults?.filter((r) => r.change_status === "changed").length ?? "…"} accent="warn" />
        <StatCard label="High priority" value={allResults?.filter((r) => r.priority_flag).length ?? "…"} accent="bad" />
      </div>

      <div className="mb-5 flex flex-wrap gap-1.5 border-b border-border pb-3">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setParams({ tab: t })}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              tab === t ? "bg-grad-brand text-white" : "text-ink-dim hover:bg-surface-2 hover:text-ink"
            }`}
          >
            {TAB_LABEL[t] ?? titleCase(t)}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="font-display text-sm font-bold text-ink">Objective</h3>
            <p className="mt-2 text-sm text-ink-dim">{agent.objective}</p>
            {agent.filters && Object.keys(agent.filters).length > 0 && (
              <>
                <h3 className="mt-5 font-display text-sm font-bold text-ink">Filters</h3>
                <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {Object.entries(agent.filters).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => (
                    <div key={k} className="rounded-lg bg-surface-2 px-3 py-2 text-xs">
                      <dt className="text-ink-mute">{titleCase(k)}</dt>
                      <dd className="mt-0.5 text-ink">{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
                    </div>
                  ))}
                </dl>
              </>
            )}
          </div>
          <div>
            <h3 className="mb-3 font-display text-sm font-bold text-ink">Recent results</h3>
            <ResultsTab agentId={agentId} />
          </div>
        </div>
      )}

      {tab === "results" && <ResultsTab agentId={agentId} />}
      {TAB_TO_CATEGORY[tab] && <ResultsTab agentId={agentId} category={TAB_TO_CATEGORY[tab]} />}
      {tab === "sources" && <SourcesTab agentId={agentId} />}
      {tab === "deadlines" && <DeadlinesTab agentId={agentId} />}
      {tab === "run_history" && <RunHistoryTable agentId={agentId} />}
      {tab === "logs" && <LogsPane agentId={agentId} />}
      {tab === "settings" && (
        <div className="card p-6">
          <h3 className="font-display text-sm font-bold text-ink">Alert rules</h3>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {agent.alert_rules.map((r) => (
              <div key={r.id} className="flex items-center justify-between rounded-lg bg-surface-2 px-3 py-2 text-xs">
                <span className="text-ink">{titleCase(r.rule_type)}</span>
                <span className="badge-mute">{r.channel}</span>
              </div>
            ))}
            {agent.alert_rules.length === 0 && <p className="text-xs text-ink-mute">No alert rules configured.</p>}
          </div>
          <button className="btn-ghost btn-sm mt-4" onClick={() => nav(`/agents/${agent.id}/edit`)}>Edit alert rules</button>

          <h3 className="mb-2 mt-6 font-display text-sm font-bold text-ink">Recent alert activity</h3>
          <AlertEventsList agentId={agentId} />
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this agent?"
        body={`"${agent.name}" and its schedule will stop running. Past results and run history stay in the database.`}
        confirmLabel="Delete agent"
        onConfirm={async () => { setConfirmDelete(false); await agentsApi.remove(agent.id); nav("/"); }}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}

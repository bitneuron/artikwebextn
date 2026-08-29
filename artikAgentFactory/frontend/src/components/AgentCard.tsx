import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AgentListItem, Template } from "../api/types";
import { relativeTime } from "../lib/format";
import { AgentStatusBadge } from "./StatusBadge";
import ConfirmDialog from "./ConfirmDialog";

export default function AgentCard({
  agent, template, index, onRun, onPause, onResume, onDuplicate, onDelete,
}: {
  agent: AgentListItem;
  template: Template | undefined;
  index: number;
  onRun: (id: number) => void;
  onPause: (id: number) => void;
  onResume: (id: number) => void;
  onDuplicate: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  const nav = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  async function act(kind: string, fn: () => void) {
    setBusy(kind);
    try {
      await Promise.resolve(fn());
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      className="card card-hover group flex animate-rise-in flex-col gap-3 p-4"
      style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}
    >
      <div className="flex items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-surface-2 text-lg">
          {template?.icon ?? "🧩"}
        </div>
        <div className="min-w-0 flex-1">
          <button
            className="truncate text-left font-display text-sm font-bold text-ink hover:text-blue-400"
            onClick={() => nav(`/agents/${agent.id}`)}
          >
            {agent.name}
          </button>
          <div className="truncate text-xs text-ink-mute">{template?.name ?? agent.template_id}</div>
        </div>
        <AgentStatusBadge status={agent.status} />
      </div>

      {agent.description && <p className="line-clamp-2 text-xs text-ink-dim">{agent.description}</p>}

      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded-lg bg-surface-2 px-2.5 py-1.5">
          <div className="text-ink-mute">Last run</div>
          <div className="font-mono text-ink">{relativeTime(agent.last_run_at)}</div>
        </div>
        <div className="rounded-lg bg-surface-2 px-2.5 py-1.5">
          <div className="text-ink-mute">Next run</div>
          <div className="font-mono text-ink">{agent.is_schedule_enabled ? relativeTime(agent.next_run_at) : "manual"}</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <span className="badge-blue">{agent.result_count_total} results</span>
        {agent.result_count_new > 0 && <span className="badge-ok">+{agent.result_count_new} new</span>}
        {agent.result_count_changed > 0 && <span className="badge-warn">{agent.result_count_changed} changed</span>}
        {agent.high_priority_count > 0 && <span className="badge-bad">{agent.high_priority_count} priority</span>}
        {agent.tags.slice(0, 2).map((t) => (
          <span key={t} className="badge-mute">#{t}</span>
        ))}
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-1.5 border-t border-border pt-3">
        {agent.can_run && (
          <button
            className="btn-ghost btn-sm"
            disabled={busy !== null}
            onClick={() => act("run", () => onRun(agent.id))}
          >
            {busy === "run" ? "Running…" : "▶ Run Now"}
          </button>
        )}
        {agent.can_manage && (
          <>
            <button className="btn-ghost btn-sm" onClick={() => nav(`/agents/${agent.id}/edit`)}>Edit</button>
            {agent.status === "active" ? (
              <button className="btn-ghost btn-sm" disabled={busy !== null} onClick={() => act("pause", () => onPause(agent.id))}>
                Pause
              </button>
            ) : agent.status === "paused" ? (
              <button className="btn-ghost btn-sm" disabled={busy !== null} onClick={() => act("resume", () => onResume(agent.id))}>
                Resume
              </button>
            ) : null}
          </>
        )}
        <button className="btn-ghost btn-sm" disabled={busy !== null} onClick={() => act("dup", () => onDuplicate(agent.id))}>
          Clone
        </button>
        <button className="btn-ghost btn-sm" onClick={() => nav(`/agents/${agent.id}?tab=logs`)}>Logs</button>
        {agent.can_manage && (
          <button className="btn-danger btn-sm ml-auto" onClick={() => setConfirmDelete(true)}>Delete</button>
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this agent?"
        body={`"${agent.name}" and its schedule will stop running. Past results and run history stay in the database.`}
        confirmLabel="Delete agent"
        onConfirm={() => { setConfirmDelete(false); onDelete(agent.id); }}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}

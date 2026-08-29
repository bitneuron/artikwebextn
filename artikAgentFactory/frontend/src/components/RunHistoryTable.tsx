import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { runsApi } from "../api/runs";
import { Run } from "../api/types";
import { formatDateTime } from "../lib/format";
import { RunStatusBadge } from "./StatusBadge";

export default function RunHistoryTable({ agentId, showAgentLink }: { agentId?: number; showAgentLink?: boolean }) {
  const nav = useNavigate();
  const [runs, setRuns] = useState<Run[] | null>(null);

  useEffect(() => {
    (agentId ? runsApi.listForAgent(agentId) : runsApi.listAll()).then(setRuns);
  }, [agentId]);

  if (runs === null) return <div className="skeleton h-40 rounded-2xl" />;

  if (runs.length === 0) {
    return (
      <div className="card flex flex-col items-center gap-2 p-10 text-center">
        <div className="text-2xl">▤</div>
        <h3 className="font-display text-sm font-bold">No runs yet</h3>
        <p className="max-w-sm text-xs text-ink-dim">Run history appears here after the first manual or scheduled run.</p>
      </div>
    );
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead className="bg-surface-2 text-xs uppercase tracking-wide text-ink-mute">
          <tr>
            <th className="px-4 py-2.5 text-left">Started</th>
            <th className="px-4 py-2.5 text-left">Trigger</th>
            <th className="px-4 py-2.5 text-left">Status</th>
            <th className="px-4 py-2.5 text-right">New</th>
            <th className="px-4 py-2.5 text-right">Changed</th>
            <th className="px-4 py-2.5 text-right">Total</th>
            <th className="px-4 py-2.5 text-right">Duration</th>
            <th className="px-4 py-2.5"></th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="border-t border-border/60">
              <td className="px-4 py-2.5 text-ink">{formatDateTime(r.started_at)}</td>
              <td className="px-4 py-2.5 capitalize text-ink-dim">{r.trigger}</td>
              <td className="px-4 py-2.5"><RunStatusBadge status={r.status} /></td>
              <td className="px-4 py-2.5 text-right font-mono text-ok">{r.result_count_new}</td>
              <td className="px-4 py-2.5 text-right font-mono text-warn">{r.result_count_changed}</td>
              <td className="px-4 py-2.5 text-right font-mono text-ink">{r.result_count_total}</td>
              <td className="px-4 py-2.5 text-right font-mono text-ink-mute">
                {r.duration_seconds ? `${Math.round(r.duration_seconds)}s` : "—"}
              </td>
              <td className="px-4 py-2.5 text-right">
                {showAgentLink && (
                  <button className="text-xs font-semibold text-blue-400 hover:underline" onClick={() => nav(`/agents/${r.agent_id}?tab=logs`)}>
                    Logs →
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

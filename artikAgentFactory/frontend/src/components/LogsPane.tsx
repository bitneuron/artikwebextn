import { useEffect, useState } from "react";
import { runsApi } from "../api/runs";
import { Run, RunLog } from "../api/types";
import { formatDateTime } from "../lib/format";

const LEVEL_CLASS: Record<string, string> = { info: "text-ink-dim", warn: "text-warn", error: "text-bad" };

export default function LogsPane({ agentId }: { agentId: number }) {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [selectedRun, setSelectedRun] = useState<number | null>(null);
  const [logs, setLogs] = useState<RunLog[] | null>(null);

  useEffect(() => {
    runsApi.listForAgent(agentId).then((rows) => {
      setRuns(rows);
      if (rows.length > 0) setSelectedRun(rows[0].id);
    });
  }, [agentId]);

  useEffect(() => {
    if (selectedRun === null) return;
    setLogs(null);
    runsApi.logs(selectedRun).then(setLogs);
  }, [selectedRun]);

  if (runs === null) return <div className="skeleton h-40 rounded-2xl" />;

  if (runs.length === 0) {
    return (
      <div className="card flex flex-col items-center gap-2 p-10 text-center">
        <div className="text-2xl">🗒️</div>
        <h3 className="font-display text-sm font-bold">No logs yet</h3>
        <p className="max-w-sm text-xs text-ink-dim">Run this agent to see a stage-by-stage execution log here.</p>
      </div>
    );
  }

  return (
    <div>
      <select
        className="select mb-3 w-auto" value={selectedRun ?? ""}
        onChange={(e) => setSelectedRun(Number(e.target.value))}
      >
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {formatDateTime(r.started_at)} — {r.status} ({r.trigger})
          </option>
        ))}
      </select>

      <div className="card overflow-x-auto p-4 font-mono text-xs">
        {logs === null && <div className="skeleton h-32 rounded-lg" />}
        {logs !== null && logs.length === 0 && <p className="text-ink-mute">No log lines for this run.</p>}
        {logs !== null && logs.map((l) => (
          <div key={l.id} className="flex gap-3 border-b border-border/40 py-1.5 last:border-0">
            <span className="shrink-0 text-ink-mute">{new Date(l.ts).toLocaleTimeString()}</span>
            <span className="w-24 shrink-0 uppercase text-ink-mute">{l.stage}</span>
            <span className={`flex-1 whitespace-pre-wrap ${LEVEL_CLASS[l.level] ?? "text-ink-dim"}`}>{l.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

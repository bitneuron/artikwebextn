import { useEffect, useState } from "react";
import { AuditEvent, auditApi } from "../api/auth";
import { formatDateTime } from "../lib/format";

const OUTCOME_BADGE: Record<string, string> = { success: "badge-ok", failure: "badge-bad", denied: "badge-warn" };

export default function AuditLog() {
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [outcome, setOutcome] = useState("");

  useEffect(() => {
    auditApi.list({ outcome: outcome || undefined }).then(setEvents);
  }, [outcome]);

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="font-display text-2xl font-extrabold tracking-tight text-ink">Audit Log</h1>
      <p className="mt-1.5 text-sm text-ink-dim">Security-relevant activity across the workspace.</p>

      <div className="mb-4 mt-6 flex gap-2">
        <select className="select w-auto" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">All outcomes</option>
          <option value="success">Success</option>
          <option value="failure">Failure</option>
          <option value="denied">Denied</option>
        </select>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-surface-2 text-xs uppercase tracking-wide text-ink-mute">
            <tr>
              <th className="px-4 py-2.5 text-left">Time</th>
              <th className="px-4 py-2.5 text-left">Actor</th>
              <th className="px-4 py-2.5 text-left">Action</th>
              <th className="px-4 py-2.5 text-left">Resource</th>
              <th className="px-4 py-2.5 text-left">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {(events ?? []).map((e) => (
              <tr key={e.id} className="border-t border-border/60">
                <td className="px-4 py-2.5 text-xs text-ink-dim">{formatDateTime(e.ts)}</td>
                <td className="px-4 py-2.5 text-xs text-ink">{e.actor_label}</td>
                <td className="px-4 py-2.5 font-mono text-xs text-ink">{e.action}</td>
                <td className="px-4 py-2.5 text-xs text-ink-mute">{e.resource_type}{e.resource_id ? `#${e.resource_id}` : ""}</td>
                <td className="px-4 py-2.5"><span className={OUTCOME_BADGE[e.outcome] ?? "badge-mute"}>{e.outcome}</span></td>
              </tr>
            ))}
            {events !== null && events.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-ink-mute">No events yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

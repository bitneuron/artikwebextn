import { useEffect, useState } from "react";
import { alertsApi } from "../api/alerts";
import { AlertEvent } from "../api/types";
import { relativeTime } from "../lib/format";

const SEVERITY_BADGE: Record<string, string> = {
  info: "badge-blue", success: "badge-ok", warning: "badge-warn", error: "badge-bad",
};

export default function AlertEventsList({ agentId }: { agentId: number }) {
  const [events, setEvents] = useState<AlertEvent[] | null>(null);

  useEffect(() => {
    alertsApi.listForAgent(agentId).then(setEvents);
  }, [agentId]);

  if (events === null) return <div className="skeleton h-24 rounded-xl" />;
  if (events.length === 0) return <p className="text-xs text-ink-mute">No alerts fired yet.</p>;

  return (
    <div className="space-y-1.5">
      {events.map((e) => (
        <div key={e.id} className="flex items-center justify-between gap-3 rounded-lg bg-surface-2 px-3 py-2 text-xs">
          <div className="flex items-center gap-2">
            <span className={SEVERITY_BADGE[e.severity] ?? "badge-mute"}>{e.severity}</span>
            <span className="text-ink">{e.title}</span>
          </div>
          <span className="shrink-0 text-ink-mute">{relativeTime(e.created_at)}{e.delivered ? "" : " · not delivered"}</span>
        </div>
      ))}
    </div>
  );
}

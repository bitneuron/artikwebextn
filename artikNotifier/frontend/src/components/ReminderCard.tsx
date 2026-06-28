import { Link } from "react-router-dom";
import type { Reminder } from "../api/types";
import { fmtDateTime, isOverdue, priorityColor, statusColor } from "../lib/format";

export default function ReminderCard({ r, onAction }: {
  r: Reminder;
  onAction: (action: string, r: Reminder) => void;
}) {
  const overdue = isOverdue(r);
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/reminders/${r.id}`} className="min-w-0 flex-1">
          <div className="truncate font-semibold hover:text-brand">{r.title}</div>
          <div className="text-xs text-slate-400">{r.category}{r.recurrence !== "one_time" && ` · ${r.recurrence}`}</div>
        </Link>
        <span className={`badge ${priorityColor[r.priority] ?? ""}`}>{r.priority}</span>
      </div>
      <div className={`text-sm ${overdue ? "font-medium text-red-500" : "text-slate-500 dark:text-slate-400"}`}>
        {overdue ? "⚠ Overdue · " : "📅 "}{fmtDateTime(r.due_at)}
      </div>
      {r.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {r.tags.map((t) => <span key={t} className="badge bg-slate-500/15 text-slate-400">#{t}</span>)}
        </div>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <span className={`badge ${statusColor[r.status] ?? ""}`}>{r.status}</span>
        <div className="ml-auto flex gap-1">
          {["active", "snoozed"].includes(r.status) && (
            <>
              <button className="btn-ghost !px-2 !py-1 !text-xs" onClick={() => onAction("complete", r)}>✓ Done</button>
              <button className="btn-ghost !px-2 !py-1 !text-xs" onClick={() => onAction("snooze", r)}>💤</button>
            </>
          )}
          {r.status === "completed" && (
            <button className="btn-ghost !px-2 !py-1 !text-xs" onClick={() => onAction("restore", r)}>↺ Restore</button>
          )}
          <button className="btn-ghost !px-2 !py-1 !text-xs" onClick={() => onAction("duplicate", r)}>⧉</button>
          <button className="btn-ghost !px-2 !py-1 !text-xs" onClick={() => onAction("delete", r)}>🗑</button>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Reminder } from "../api/types";
import { fmtDateTime, isOverdue, priorityColor, statusColor } from "../lib/format";
import { reminderAction } from "../lib/reminders";

export default function ReminderDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [r, setR] = useState<Reminder | null>(null);

  async function load() {
    try { setR(await api.get<Reminder>(`/api/reminders/${id}`)); }
    catch { nav("/reminders"); }
  }
  useEffect(() => { load(); }, [id]);
  if (!r) return <div className="text-slate-400">Loading…</div>;

  async function act(action: string) {
    const reload = await reminderAction(action, r!);
    if (action === "delete" && reload) { nav("/reminders"); return; }
    if (reload) load();
  }

  const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="text-slate-400">{k}</span><span className="text-right">{v}</span>
    </div>
  );

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <Link to="/reminders" className="text-sm text-brand">← Back to reminders</Link>
      <div className="card space-y-3">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-xl font-bold">{r.title}</h1>
          <span className={`badge ${priorityColor[r.priority]}`}>{r.priority}</span>
        </div>
        <div className={`text-sm ${isOverdue(r) ? "font-medium text-red-500" : "text-slate-500"}`}>
          {isOverdue(r) ? "⚠ Overdue · " : "📅 "}{fmtDateTime(r.due_at)}
        </div>
        {r.description && <p className="text-sm">{r.description}</p>}
        {r.notes && <div className="rounded-lg bg-slate-100 p-3 text-sm dark:bg-slate-800/50"><b className="text-slate-400">Notes</b><br />{r.notes}</div>}
        <div className="border-t border-slate-100 pt-2 dark:border-slate-800">
          <Row k="Status" v={<span className={`badge ${statusColor[r.status] ?? ""}`}>{r.status}</span>} />
          <Row k="Category" v={r.category} />
          <Row k="Recurrence" v={r.recurrence.replace("_", " ")} />
          <Row k="Schedule" v={r.schedule.join(", ")} />
          <Row k="Channels" v={r.channels.join(", ")} />
          <Row k="Tags" v={r.tags.length ? r.tags.map((t) => `#${t}`).join(" ") : "—"} />
          <Row k="Created" v={fmtDateTime(r.created_at)} />
        </div>
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
          <Link to={`/reminders/${r.id}/edit`} className="btn-ghost !py-1.5">✏️ Edit</Link>
          {["active", "snoozed"].includes(r.status) && (
            <>
              <button className="btn-ghost !py-1.5" onClick={() => act("complete")}>✓ Complete</button>
              <button className="btn-ghost !py-1.5" onClick={() => act("snooze")}>💤 Snooze</button>
              <button className="btn-ghost !py-1.5" onClick={() => act("archive")}>📥 Archive</button>
            </>
          )}
          {["completed", "archived"].includes(r.status) && (
            <button className="btn-ghost !py-1.5" onClick={() => act("restore")}>↺ Restore</button>
          )}
          <button className="btn-ghost !py-1.5" onClick={() => act("duplicate")}>⧉ Duplicate</button>
          <button className="btn-ghost !py-1.5 text-red-500" onClick={() => act("delete")}>🗑 Delete</button>
        </div>
      </div>
    </div>
  );
}

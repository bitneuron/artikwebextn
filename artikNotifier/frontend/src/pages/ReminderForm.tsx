import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Options, Reminder } from "../api/types";
import { toInputDateTime } from "../lib/format";

const SCHEDULE_LABELS: Record<string, string> = {
  on_due: "On due date", "1_day": "1 day before", "2_days": "2 days before", "3_days": "3 days before",
  "1_week": "1 week before", "2_weeks": "2 weeks before", "1_month": "1 month before",
};
const CHANNEL_LABELS: Record<string, string> = { email: "Email", in_app: "In-app" };

export default function ReminderForm() {
  const { id } = useParams();
  const editing = Boolean(id);
  const nav = useNavigate();
  const [options, setOptions] = useState<Options | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    title: "", description: "", notes: "", category: "Personal", priority: "medium",
    due_at: toInputDateTime(new Date(Date.now() + 86400000).toISOString()),
    recurrence: "one_time", schedule: ["on_due"] as string[],
    channels: ["email", "in_app"] as string[], tags: "" as string,
  });

  useEffect(() => { api.get<Options>("/api/options").then(setOptions); }, []);
  useEffect(() => {
    if (!editing) return;
    api.get<Reminder>(`/api/reminders/${id}`).then((r) => setForm({
      title: r.title, description: r.description ?? "", notes: r.notes ?? "", category: r.category,
      priority: r.priority, due_at: toInputDateTime(r.due_at), recurrence: r.recurrence,
      schedule: r.schedule, channels: r.channels, tags: r.tags.join(", "),
    }));
  }, [id]);

  function toggle(field: "schedule" | "channels", value: string) {
    setForm((f) => {
      const arr = f[field];
      return { ...f, [field]: arr.includes(value) ? arr.filter((x) => x !== value) : [...arr, value] };
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    const payload = {
      ...form,
      due_at: new Date(form.due_at).toISOString(),
      schedule: form.schedule.length ? form.schedule : ["on_due"],
      tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
    };
    try {
      const saved = editing
        ? await api.put<Reminder>(`/api/reminders/${id}`, payload)
        : await api.post<Reminder>("/api/reminders", payload);
      nav(`/reminders/${saved.id}`);
    } catch (e: any) { setErr(e.message || "Save failed"); }
    finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-bold">{editing ? "Edit reminder" : "New reminder"}</h1>
      <div className="card space-y-4">
        <div>
          <label className="label">Title *</label>
          <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required autoFocus />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Category</label>
            <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {options?.categories.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Priority</label>
            <select className="input" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {options?.priorities.map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Due date & time *</label>
            <input className="input" type="datetime-local" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} required />
          </div>
          <div>
            <label className="label">Recurrence</label>
            <select className="input" value={form.recurrence} onChange={(e) => setForm({ ...form, recurrence: e.target.value })}>
              {options?.recurrences.map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="label">Description</label>
          <textarea className="input" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div>
          <label className="label">Notes</label>
          <textarea className="input" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <div>
          <label className="label">Tags (comma separated)</label>
          <input className="input" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="home, money" />
        </div>
        <div>
          <label className="label">Reminder schedule</label>
          <div className="flex flex-wrap gap-2">
            {(options?.schedule_offsets ?? []).map((s) => (
              <button type="button" key={s} onClick={() => toggle("schedule", s)}
                className={`badge cursor-pointer border ${form.schedule.includes(s) ? "border-brand bg-brand/15 text-brand" : "border-slate-300 text-slate-500 dark:border-slate-700"}`}>
                {SCHEDULE_LABELS[s] ?? s}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="label">Notification channels</label>
          <div className="flex flex-wrap gap-2">
            {(options?.channels ?? ["email", "in_app"]).map((c) => (
              <button type="button" key={c} onClick={() => toggle("channels", c)}
                className={`badge cursor-pointer border ${form.channels.includes(c) ? "border-brand bg-brand/15 text-brand" : "border-slate-300 text-slate-500 dark:border-slate-700"}`}>
                {CHANNEL_LABELS[c] ?? c}
              </button>
            ))}
          </div>
        </div>
        {err && <p className="text-sm text-red-500">{err}</p>}
        <div className="flex gap-2">
          <button className="btn-primary" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Create reminder"}</button>
          <button type="button" className="btn-ghost" onClick={() => nav(-1)}>Cancel</button>
        </div>
      </div>
    </form>
  );
}

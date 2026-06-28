import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Options, Reminder } from "../api/types";
import ReminderCard from "../components/ReminderCard";
import { reminderAction } from "../lib/reminders";

export default function Reminders() {
  const [items, setItems] = useState<Reminder[]>([]);
  const [options, setOptions] = useState<Options | null>(null);
  const [q, setQ] = useState({ status: "", category: "", priority: "", search: "", sort: "due_at", order: "asc" });

  async function load() {
    const params = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v && params.set(k, v));
    setItems(await api.get<Reminder[]>(`/api/reminders?${params.toString()}`));
  }
  useEffect(() => { api.get<Options>("/api/options").then(setOptions); }, []);
  useEffect(() => { load(); }, [q]);

  async function act(action: string, r: Reminder) { if (await reminderAction(action, r)) load(); }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Reminders</h1>
        <Link to="/reminders/new" className="btn-primary">+ New</Link>
      </div>

      <div className="card grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <input className="input col-span-2 sm:col-span-2" placeholder="Search…" value={q.search}
          onChange={(e) => setQ({ ...q, search: e.target.value })} />
        <select className="input" value={q.status} onChange={(e) => setQ({ ...q, status: e.target.value })}>
          <option value="">All status</option>
          {["active", "snoozed", "completed", "archived"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="input" value={q.category} onChange={(e) => setQ({ ...q, category: e.target.value })}>
          <option value="">All categories</option>
          {options?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="input" value={q.priority} onChange={(e) => setQ({ ...q, priority: e.target.value })}>
          <option value="">All priorities</option>
          {options?.priorities.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="input" value={`${q.sort}:${q.order}`}
          onChange={(e) => { const [sort, order] = e.target.value.split(":"); setQ({ ...q, sort, order }); }}>
          <option value="due_at:asc">Due ↑</option>
          <option value="due_at:desc">Due ↓</option>
          <option value="priority:desc">Priority</option>
          <option value="created_at:desc">Newest</option>
        </select>
      </div>

      {items.length === 0 ? (
        <p className="card text-center text-slate-400">No reminders. <Link to="/reminders/new" className="text-brand">Create one →</Link></p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((r) => <ReminderCard key={r.id} r={r} onAction={act} />)}
        </div>
      )}
    </div>
  );
}

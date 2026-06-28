import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Notification } from "../api/types";
import { fmtDateTime } from "../lib/format";

const STATUS_COLOR: Record<string, string> = {
  sent: "bg-emerald-500/15 text-emerald-500", read: "bg-slate-500/15 text-slate-400",
  pending: "bg-amber-500/15 text-amber-500", failed: "bg-red-500/15 text-red-500",
};

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[]>([]);
  const [filter, setFilter] = useState({ status: "", unread_only: false, search: "" });

  async function load() {
    const p = new URLSearchParams();
    if (filter.status) p.set("status", filter.status);
    if (filter.unread_only) p.set("unread_only", "true");
    if (filter.search) p.set("search", filter.search);
    setItems(await api.get<Notification[]>(`/api/notifications?${p}`));
  }
  useEffect(() => { load(); }, [filter]);

  async function markRead(id: number) { await api.post(`/api/notifications/${id}/read`); load(); }
  async function del(id: number) { await api.del(`/api/notifications/${id}`); load(); }
  async function markAll() { await api.post("/api/notifications/read-all"); load(); }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Notification Center</h1>
        <button className="btn-ghost" onClick={markAll}>Mark all read</button>
      </div>

      <div className="card flex flex-wrap gap-2">
        <input className="input flex-1" placeholder="Search…" value={filter.search} onChange={(e) => setFilter({ ...filter, search: e.target.value })} />
        <select className="input w-40" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
          <option value="">All statuses</option>
          {["pending", "sent", "read", "failed", "archived"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={filter.unread_only} onChange={(e) => setFilter({ ...filter, unread_only: e.target.checked })} /> Unread only</label>
      </div>

      <div className="card divide-y divide-slate-100 dark:divide-slate-800">
        {items.length === 0 && <p className="py-6 text-center text-sm text-slate-400">No notifications.</p>}
        {items.map((n) => (
          <div key={n.id} className={`flex items-center gap-3 py-3 ${n.is_read ? "opacity-60" : ""}`}>
            <div className="min-w-0 flex-1">
              <div className="font-medium">{n.title}</div>
              {n.body && <div className="truncate text-xs text-slate-400">{n.body}</div>}
              <div className="mt-0.5 text-xs text-slate-400">{n.channel} · {fmtDateTime(n.created_at)}</div>
            </div>
            <span className={`badge ${STATUS_COLOR[n.status] ?? ""}`}>{n.status}</span>
            {!n.is_read && <button className="text-xs text-brand" onClick={() => markRead(n.id)}>read</button>}
            <button className="text-xs text-red-500" onClick={() => del(n.id)}>🗑</button>
          </div>
        ))}
      </div>
    </div>
  );
}

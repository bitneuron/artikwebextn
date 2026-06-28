import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Bell } from "../api/types";
import { fmtDateTime } from "../lib/format";

export default function NotificationBell() {
  const [bell, setBell] = useState<Bell | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  async function load() {
    try { setBell(await api.get<Bell>("/api/notifications/bell")); } catch { /* ignore */ }
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("click", onClick);
    return () => { clearInterval(t); document.removeEventListener("click", onClick); };
  }, []);

  async function markAll() { await api.post("/api/notifications/read-all"); load(); }
  async function markRead(id: number) { await api.post(`/api/notifications/${id}/read`); load(); }

  const unread = bell?.unread_count ?? 0;
  return (
    <div className="relative" ref={ref}>
      <button className="relative text-xl" onClick={() => setOpen((o) => !o)} aria-label="Notifications">
        🔔
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 min-w-[16px] rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-[#161b22]">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2 dark:border-slate-800">
            <span className="text-sm font-semibold">Notifications</span>
            <button className="text-xs text-brand" onClick={markAll}>Mark all read</button>
          </div>
          <div className="flex gap-3 px-3 py-2 text-xs text-slate-500">
            <span>📌 Due: {bell?.due_count ?? 0}</span>
            <span className="text-red-500">⚠ Overdue: {bell?.overdue_count ?? 0}</span>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {(bell?.recent ?? []).length === 0 && <div className="p-4 text-center text-sm text-slate-400">No notifications</div>}
            {(bell?.recent ?? []).map((n) => (
              <div key={n.id} className={`border-b border-slate-100 px-3 py-2 dark:border-slate-800 ${n.is_read ? "opacity-60" : ""}`}>
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">{n.title}</div>
                  {!n.is_read && <button className="text-[11px] text-brand" onClick={() => markRead(n.id)}>read</button>}
                </div>
                <div className="text-xs text-slate-400">{n.channel} · {fmtDateTime(n.created_at)}</div>
              </div>
            ))}
          </div>
          <Link to="/notifications" className="block border-t border-slate-100 px-3 py-2 text-center text-xs text-brand dark:border-slate-800" onClick={() => setOpen(false)}>
            View all →
          </Link>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Dashboard } from "../api/types";
import ReminderCard from "../components/ReminderCard";
import { reminderAction } from "../lib/reminders";
import { fmtDateTime } from "../lib/format";

const STAT = [
  { key: "upcoming", label: "Upcoming", icon: "📅", color: "text-blue-500" },
  { key: "due_today", label: "Due Today", icon: "📌", color: "text-amber-500" },
  { key: "overdue", label: "Overdue", icon: "⚠️", color: "text-red-500" },
  { key: "completed", label: "Completed", icon: "✅", color: "text-emerald-500" },
  { key: "unread", label: "Unread", icon: "🔔", color: "text-violet-500" },
];

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);

  async function load() { setData(await api.get<Dashboard>("/api/dashboard")); }
  useEffect(() => { load(); }, []);

  async function act(action: string, r: any) { if (await reminderAction(action, r)) load(); }

  if (!data) return <div className="text-slate-400">Loading…</div>;

  const Section = ({ title, items, empty }: { title: string; items: any[]; empty: string }) => (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-slate-500">{title}</h2>
      {items.length === 0 ? (
        <p className="card text-sm text-slate-400">{empty}</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((r) => <ReminderCard key={r.id} r={r} onAction={act} />)}
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {STAT.map((s) => (
          <div key={s.key} className="card">
            <div className="text-xs text-slate-400">{s.icon} {s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{data.counts[s.key] ?? 0}</div>
          </div>
        ))}
      </div>

      {data.overdue.length > 0 && <Section title="⚠️ Overdue" items={data.overdue} empty="" />}
      <Section title="📌 Due Today" items={data.due_today} empty="Nothing due today 🎉" />
      <Section title="📅 Upcoming (7 days)" items={data.upcoming} empty="No upcoming reminders." />

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Recent Activity</h2>
        <div className="card divide-y divide-slate-100 dark:divide-slate-800">
          {data.recent_activity.length === 0 && <p className="text-sm text-slate-400">No recent activity.</p>}
          {data.recent_activity.map((n) => (
            <div key={n.id} className="flex items-center justify-between py-2 text-sm">
              <span>{n.title}</span>
              <span className="text-xs text-slate-400">{n.channel} · {fmtDateTime(n.created_at)}</span>
            </div>
          ))}
        </div>
        <Link to="/notifications" className="mt-2 inline-block text-xs text-brand">View notification center →</Link>
      </div>
    </div>
  );
}

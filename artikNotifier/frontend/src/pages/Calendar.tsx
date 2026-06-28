import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { CalendarMonth } from "../api/types";
import { priorityColor } from "../lib/format";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];

export default function CalendarPage() {
  const now = new Date();
  const [ym, setYm] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [data, setData] = useState<CalendarMonth | null>(null);

  useEffect(() => {
    api.get<CalendarMonth>(`/api/calendar?year=${ym.year}&month=${ym.month}`).then(setData);
  }, [ym]);

  function shift(delta: number) {
    let m = ym.month + delta, y = ym.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    setYm({ year: y, month: m });
  }

  const firstWeekday = new Date(ym.year, ym.month - 1, 1).getDay();
  const today = new Date();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{MONTHS[ym.month - 1]} {ym.year}</h1>
        <div className="flex gap-2">
          <button className="btn-ghost !px-3 !py-1.5" onClick={() => shift(-1)}>←</button>
          <button className="btn-ghost !px-3 !py-1.5" onClick={() => setYm({ year: now.getFullYear(), month: now.getMonth() + 1 })}>Today</button>
          <button className="btn-ghost !px-3 !py-1.5" onClick={() => shift(1)}>→</button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center text-xs font-semibold text-slate-400">
        {WEEKDAYS.map((d) => <div key={d}>{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: firstWeekday }).map((_, i) => <div key={`e${i}`} />)}
        {(data?.days ?? []).map((day) => {
          const d = new Date(day.date);
          const isToday = d.toDateString() === today.toDateString();
          return (
            <div key={day.date} className={`min-h-[84px] rounded-lg border p-1 text-left ${isToday ? "border-brand bg-brand/5" : "border-slate-200 dark:border-slate-800"}`}>
              <div className={`mb-1 text-xs ${isToday ? "font-bold text-brand" : "text-slate-400"}`}>{d.getDate()}</div>
              <div className="space-y-0.5">
                {day.reminders.slice(0, 3).map((r) => (
                  <Link key={r.id} to={`/reminders/${r.id}`} className={`block truncate rounded px-1 text-[10px] ${priorityColor[r.priority] ?? "bg-slate-500/15"}`}>
                    {r.title}
                  </Link>
                ))}
                {day.reminders.length > 3 && <div className="px-1 text-[10px] text-slate-400">+{day.reminders.length - 3} more</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

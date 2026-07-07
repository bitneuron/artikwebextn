import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { CalendarMonth, QuickNote } from "../api/types";
import { priorityColor } from "../lib/format";

type NoteRem = { id: number; title: string; time: string | null };

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];

export default function CalendarPage() {
  const now = new Date();
  const [ym, setYm] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [data, setData] = useState<CalendarMonth | null>(null);
  const [noteRem, setNoteRem] = useState<Record<string, NoteRem[]>>({});

  useEffect(() => {
    api.get<CalendarMonth>(`/api/calendar?year=${ym.year}&month=${ym.month}`).then(setData);
  }, [ym]);

  // Notes-with-reminders for the visible month → bucketed by due_date (notes-first: a note's
  // reminder shows on the calendar and clicking it opens the note).
  useEffect(() => {
    const mm = String(ym.month).padStart(2, "0");
    const last = new Date(ym.year, ym.month, 0).getDate();
    const from = `${ym.year}-${mm}-01`;
    const to = `${ym.year}-${mm}-${String(last).padStart(2, "0")}`;
    api.get<QuickNote[]>(`/api/notes?has_reminder=true&due_from=${from}&due_to=${to}&limit=200`).then((ns) => {
      const map: Record<string, NoteRem[]> = {};
      ns.forEach((n) => {
        if (n.due_date) (map[n.due_date] ??= []).push({ id: n.id, title: n.title || n.note_text.slice(0, 30) || "Untitled", time: n.due_time });
      });
      setNoteRem(map);
    });
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
                {day.reminders.slice(0, 2).map((r) => (
                  <Link key={r.id} to={`/reminders/${r.id}`} className={`block truncate rounded px-1 text-[10px] ${priorityColor[r.priority] ?? "bg-slate-500/15"}`}>
                    {r.title}
                  </Link>
                ))}
                {(noteRem[day.date.slice(0, 10)] ?? []).slice(0, 3).map((n) => (
                  <Link key={`n${n.id}`} to={`/notes?note=${n.id}`}
                    className="block truncate rounded bg-amber-500/20 px-1 text-[10px] font-medium text-amber-600 dark:text-amber-300"
                    title={n.title}>
                    ⏰ {n.time ? `${n.time} ` : ""}{n.title}
                  </Link>
                ))}
                {(day.reminders.length > 2 || (noteRem[day.date.slice(0, 10)]?.length ?? 0) > 3) && (
                  <div className="px-1 text-[10px] text-slate-400">
                    +{Math.max(0, day.reminders.length - 2) + Math.max(0, (noteRem[day.date.slice(0, 10)]?.length ?? 0) - 3)} more
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

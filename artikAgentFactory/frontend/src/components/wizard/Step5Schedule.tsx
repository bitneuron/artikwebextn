import { ScheduleConfig } from "../../api/types";
import { scheduleSummary } from "../../lib/format";

const PRESETS: { value: NonNullable<ScheduleConfig["preset"]>; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "biweekly", label: "Twice weekly" },
  { value: "monthly", label: "Monthly" },
];

export default function Step5Schedule({
  schedule, runImmediately, onChange, onRunImmediately,
}: { schedule: ScheduleConfig; runImmediately: boolean; onChange: (s: ScheduleConfig) => void; onRunImmediately: (v: boolean) => void }) {
  return (
    <div className="space-y-5">
      <h2 className="font-display text-lg font-bold text-ink">Schedule</h2>

      <div className="grid grid-cols-3 gap-2">
        {(["manual", "preset", "interval"] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => onChange(mode === "manual" ? { mode } : mode === "preset" ? { mode, preset: "weekly", hour_utc: 9 } : { mode, interval_minutes: 60 })}
            className={`rounded-xl border px-3 py-2.5 text-sm font-semibold capitalize transition ${
              schedule.mode === mode ? "border-blue/50 bg-blue/10 text-ink" : "border-border bg-surface-2 text-ink-dim hover:border-border-hover"
            }`}
          >
            {mode === "manual" ? "Manual only" : mode === "preset" ? "Recurring" : "Interval"}
          </button>
        ))}
      </div>

      {schedule.mode === "preset" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="sched-preset">Frequency</label>
            <select id="sched-preset" className="select" value={schedule.preset ?? "weekly"}
              onChange={(e) => onChange({ ...schedule, preset: e.target.value as ScheduleConfig["preset"] })}>
              {PRESETS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="sched-hour">Time (UTC)</label>
            <input id="sched-hour" type="number" min={0} max={23} className="input" value={schedule.hour_utc ?? 9}
              onChange={(e) => onChange({ ...schedule, hour_utc: Number(e.target.value) })} />
          </div>
        </div>
      )}

      {schedule.mode === "interval" && (
        <div>
          <label className="label" htmlFor="sched-interval">Every N minutes</label>
          <input id="sched-interval" type="number" min={15} className="input" value={schedule.interval_minutes ?? 60}
            onChange={(e) => onChange({ ...schedule, interval_minutes: Number(e.target.value) })} />
        </div>
      )}

      <div className="rounded-lg bg-surface-2 px-4 py-3 text-sm text-ink">
        <span className="text-ink-mute">Summary: </span>{scheduleSummary(schedule)}
      </div>

      <div className="flex items-center gap-3 rounded-xl border border-border bg-surface-2 px-4 py-3">
        <input id="run-immediately" type="checkbox" className="h-4 w-4 accent-blue" checked={runImmediately}
          onChange={(e) => onRunImmediately(e.target.checked)} />
        <label htmlFor="run-immediately" className="text-sm text-ink">Run immediately after creation</label>
      </div>
    </div>
  );
}

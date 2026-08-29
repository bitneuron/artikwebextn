export function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const diffMs = Date.now() - then;
  const future = diffMs < 0;
  const abs = Math.abs(diffMs);
  const mins = Math.round(abs / 60000);
  const hrs = Math.round(mins / 60);
  const days = Math.round(hrs / 24);
  let out: string;
  if (mins < 1) out = "just now";
  else if (mins < 60) out = `${mins}m`;
  else if (hrs < 24) out = `${hrs}h`;
  else if (days < 30) out = `${days}d`;
  else out = new Date(iso).toLocaleDateString();
  if (out === "just now") return out;
  return future ? `in ${out}` : `${out} ago`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export function scheduleSummary(schedule: { mode: string; preset?: string; interval_minutes?: number; hour_utc?: number }): string {
  if (!schedule || schedule.mode === "manual") return "Manual only";
  if (schedule.mode === "interval") return `Every ${schedule.interval_minutes ?? 60} min`;
  if (schedule.mode === "preset") {
    const hour = schedule.hour_utc ?? 9;
    const label = { daily: "Daily", weekly: "Weekly", biweekly: "Twice weekly", monthly: "Monthly" }[schedule.preset ?? "daily"] ?? "Scheduled";
    return `${label} · ${String(hour).padStart(2, "0")}:00 UTC`;
  }
  return "Scheduled";
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

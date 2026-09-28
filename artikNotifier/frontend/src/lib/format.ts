export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
export function toInputDateTime(iso: string): string {
  // → "YYYY-MM-DDTHH:mm" for <input type=datetime-local>
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export const priorityColor: Record<string, string> = {
  low: "bg-slate-500/15 text-slate-500",
  medium: "bg-blue-500/15 text-blue-500",
  high: "bg-amber-500/15 text-amber-500",
  critical: "bg-red-500/15 text-red-500",
};
export const statusColor: Record<string, string> = {
  active: "bg-emerald-500/15 text-emerald-500",
  snoozed: "bg-violet-500/15 text-violet-400",
  completed: "bg-slate-500/15 text-slate-400",
  archived: "bg-slate-500/15 text-slate-400",
};

export function isOverdue(r: { due_at: string; status: string }): boolean {
  return ["active", "snoozed"].includes(r.status) && new Date(r.due_at) < new Date();
}

export default function StatCard({
  label, value, accent = "blue", hint,
}: { label: string; value: string | number; accent?: "blue" | "violet" | "ok" | "warn" | "bad"; hint?: string }) {
  const ring: Record<string, string> = {
    blue: "from-blue/15 to-transparent text-blue-400",
    violet: "from-violet/15 to-transparent text-violet-400",
    ok: "from-ok/15 to-transparent text-ok",
    warn: "from-warn/15 to-transparent text-warn",
    bad: "from-bad/15 to-transparent text-bad",
  };
  return (
    <div className="card relative overflow-hidden p-4">
      <div className={`pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-gradient-to-br ${ring[accent]} blur-2xl`} />
      <div className="relative">
        <div className="text-xs font-semibold uppercase tracking-wide text-ink-mute">{label}</div>
        <div className="mt-1.5 font-mono text-2xl font-semibold text-ink">{value}</div>
        {hint && <div className="mt-0.5 text-[11px] text-ink-mute">{hint}</div>}
      </div>
    </div>
  );
}

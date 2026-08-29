import { AgentDraft, Template } from "../../api/types";
import { scheduleSummary, titleCase } from "../../lib/format";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-border/60 py-2 text-sm last:border-0">
      <span className="text-ink-mute">{label}</span>
      <span className="max-w-[65%] text-right text-ink">{value || "—"}</span>
    </div>
  );
}

export default function Step7Review({ draft, template }: { draft: AgentDraft; template: Template | undefined }) {
  const filterEntries = Object.entries(draft.filters).filter(([, v]) => v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0));
  const profileEntries = draft.profile ? Object.entries(draft.profile).filter(([, v]) => v) : [];

  return (
    <div className="space-y-5">
      <h2 className="font-display text-lg font-bold text-ink">Review</h2>

      <div className="rounded-xl border border-border bg-surface-2 p-4">
        <div className="flex items-center gap-2.5">
          <span className="text-lg">{template?.icon}</span>
          <div>
            <div className="font-display text-sm font-bold text-ink">{draft.name || "Untitled agent"}</div>
            <div className="text-xs text-ink-mute">{template?.name}</div>
          </div>
        </div>
        <p className="mt-2.5 text-sm text-ink-dim">{draft.objective}</p>
      </div>

      <div className="rounded-xl border border-border p-4">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-mute">Filters</h3>
        {filterEntries.length === 0 && <p className="text-sm text-ink-mute">None configured</p>}
        {filterEntries.map(([k, v]) => <Row key={k} label={titleCase(k)} value={Array.isArray(v) ? v.join(", ") : String(v)} />)}
      </div>

      {draft.profile && (
        <div className="rounded-xl border border-border p-4">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-mute">Profile</h3>
          {profileEntries.length === 0 && <p className="text-sm text-ink-mute">Enabled, no fields filled in yet</p>}
          {profileEntries.map(([k, v]) => <Row key={k} label={titleCase(k)} value={String(v)} />)}
        </div>
      )}

      <div className="rounded-xl border border-border p-4">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-mute">Schedule</h3>
        <Row label="Runs" value={scheduleSummary(draft.schedule)} />
        <Row label="Run immediately" value={draft.run_immediately ? "Yes" : "No"} />
      </div>

      <div className="rounded-xl border border-border p-4">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-mute">Alerts</h3>
        {draft.alert_rules.length === 0 && <p className="text-sm text-ink-mute">None configured</p>}
        {draft.alert_rules.map((r) => (
          <Row key={r.rule_type} label={titleCase(r.rule_type)} value={r.channel} />
        ))}
      </div>
    </div>
  );
}

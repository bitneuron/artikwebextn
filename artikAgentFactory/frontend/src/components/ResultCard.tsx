import { useState } from "react";
import { Result } from "../api/types";
import { formatDate, relativeTime, titleCase } from "../lib/format";

const CHANGE_BADGE: Record<string, string> = { new: "badge-ok", changed: "badge-warn", unchanged: "badge-mute" };
const CRED_BADGE: Record<string, string> = { high: "badge-ok", medium: "badge-blue", low: "badge-mute" };

export default function ResultCard({
  result, index, onSave, onDismiss,
}: { result: Result; index: number; onSave: (id: number, saved: boolean) => void; onDismiss: (id: number, dismissed: boolean) => void }) {
  const [expanded, setExpanded] = useState(false);
  const fieldEntries = Object.entries(result.fields || {}).filter(([, v]) => v !== null && v !== "" && v !== undefined);
  const changedKeys = Object.keys(result.changed_fields || {});

  return (
    <div
      className="card card-hover animate-rise-in p-4"
      style={{ animationDelay: `${Math.min(index, 10) * 30}ms` }}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={CHANGE_BADGE[result.change_status]}>{result.change_status}</span>
            {result.priority_flag && <span className="badge-bad">priority</span>}
            <span className={CRED_BADGE[result.source_credibility]}>{result.source_credibility} credibility</span>
            <span className="badge-mute">{titleCase(result.category)}</span>
          </div>
          <a
            href={result.url} target="_blank" rel="noreferrer"
            className="mt-1.5 block text-sm font-bold text-ink hover:text-blue-400"
          >
            {result.title}
          </a>
          {result.summary && <p className="mt-1 text-xs leading-relaxed text-ink-dim">{result.summary}</p>}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 text-right">
          <span className="badge-violet font-mono">{Math.round(result.relevance_score * 100)}% rel</span>
          <span className="text-[10px] text-ink-mute">{Math.round(result.confidence_score * 100)}% confidence</span>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-ink-mute">
        {result.source_name && <span>{result.source_name}</span>}
        {result.published_or_updated_at && <span>· {formatDate(result.published_or_updated_at)}</span>}
        <span>· seen {relativeTime(result.updated_at)}</span>
      </div>

      {changedKeys.length > 0 && (
        <div className="mt-2 rounded-lg bg-warn/10 px-3 py-2 text-[11px] text-warn">
          Changed: {changedKeys.map((k) => titleCase(k)).join(", ")}
        </div>
      )}

      {fieldEntries.length > 0 && (
        <button className="mt-2 text-[11px] font-semibold text-blue-400 hover:underline" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Hide details ▲" : "Show details ▼"}
        </button>
      )}
      {expanded && (
        <dl className="mt-2 grid grid-cols-1 gap-1.5 rounded-lg bg-surface-2 p-3 sm:grid-cols-2">
          {fieldEntries.map(([k, v]) => (
            <div key={k} className="text-xs">
              <dt className="text-ink-mute">{titleCase(k)}</dt>
              <dd className="text-ink">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mt-3 flex items-center gap-1.5 border-t border-border pt-3">
        <button className={result.is_saved ? "badge-blue" : "btn-ghost btn-sm"} onClick={() => onSave(result.id, !result.is_saved)}>
          {result.is_saved ? "★ Saved" : "☆ Save"}
        </button>
        <button className="btn-ghost btn-sm" onClick={() => onDismiss(result.id, !result.is_dismissed)}>
          {result.is_dismissed ? "Restore" : "Dismiss"}
        </button>
        <a href={result.url} target="_blank" rel="noreferrer" className="btn-ghost btn-sm ml-auto">Open source ↗</a>
      </div>
    </div>
  );
}

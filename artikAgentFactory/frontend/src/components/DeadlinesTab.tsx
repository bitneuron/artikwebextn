import { useEffect, useMemo, useState } from "react";
import { resultsApi } from "../api/results";
import { Result } from "../api/types";
import { formatDate, titleCase } from "../lib/format";

const DEADLINE_KEYS = ["deadline", "application_deadline", "expiration", "scholarship_deadline"];

export default function DeadlinesTab({ agentId }: { agentId: number }) {
  const [results, setResults] = useState<Result[] | null>(null);

  useEffect(() => {
    resultsApi.list(agentId, { sort: "created_at", order: "desc" }).then(setResults);
  }, [agentId]);

  const withDeadlines = useMemo(() => {
    if (!results) return [];
    const rows: { result: Result; key: string; value: string; date: Date | null }[] = [];
    for (const r of results) {
      for (const k of DEADLINE_KEYS) {
        const v = (r.fields as Record<string, unknown>)[k];
        if (v) {
          const d = new Date(String(v));
          rows.push({ result: r, key: k, value: String(v), date: isNaN(d.getTime()) ? null : d });
          break;
        }
      }
    }
    return rows.sort((a, b) => (a.date?.getTime() ?? Infinity) - (b.date?.getTime() ?? Infinity));
  }, [results]);

  if (results === null) return <div className="skeleton h-40 rounded-2xl" />;

  if (withDeadlines.length === 0) {
    return (
      <div className="card flex flex-col items-center gap-2 p-10 text-center">
        <div className="text-2xl">🗓️</div>
        <h3 className="font-display text-sm font-bold">No deadlines tracked</h3>
        <p className="max-w-sm text-xs text-ink-dim">Results with a deadline-shaped field show up here, soonest first.</p>
      </div>
    );
  }

  const now = Date.now();

  return (
    <div className="grid grid-cols-1 gap-2">
      {withDeadlines.map(({ result, key, value, date }) => {
        const daysAway = date ? Math.round((date.getTime() - now) / 86400000) : null;
        const urgent = daysAway !== null && daysAway <= 14 && daysAway >= 0;
        const past = daysAway !== null && daysAway < 0;
        return (
          <a
            key={result.id + key} href={result.url} target="_blank" rel="noreferrer"
            className="card card-hover flex items-center justify-between gap-3 p-3.5"
          >
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-ink">{result.title}</div>
              <div className="text-xs text-ink-mute">{titleCase(key)}</div>
            </div>
            <div className="shrink-0 text-right">
              <div className="font-mono text-sm text-ink">{date ? formatDate(date.toISOString()) : value}</div>
              {daysAway !== null && (
                <div className={`text-[11px] ${past ? "text-ink-mute" : urgent ? "text-warn" : "text-ink-dim"}`}>
                  {past ? "past" : `${daysAway}d away`}
                </div>
              )}
            </div>
          </a>
        );
      })}
    </div>
  );
}

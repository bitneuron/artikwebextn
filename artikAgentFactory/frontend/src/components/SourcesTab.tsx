import { useEffect, useState } from "react";
import { resultsApi, SourceSummary } from "../api/results";

const CRED_BADGE: Record<string, string> = { high: "badge-ok", medium: "badge-blue", low: "badge-mute" };

export default function SourcesTab({ agentId }: { agentId: number }) {
  const [sources, setSources] = useState<SourceSummary[] | null>(null);

  useEffect(() => {
    resultsApi.sources(agentId).then(setSources);
  }, [agentId]);

  if (sources === null) return <div className="skeleton h-40 rounded-2xl" />;

  if (sources.length === 0) {
    return (
      <div className="card flex flex-col items-center gap-2 p-10 text-center">
        <div className="text-2xl">📚</div>
        <h3 className="font-display text-sm font-bold">No sources yet</h3>
        <p className="max-w-sm text-xs text-ink-dim">Sources appear here once this agent has run.</p>
      </div>
    );
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[480px] text-sm">
        <thead className="bg-surface-2 text-xs uppercase tracking-wide text-ink-mute">
          <tr>
            <th className="px-4 py-2.5 text-left">Source</th>
            <th className="px-4 py-2.5 text-left">Domain</th>
            <th className="px-4 py-2.5 text-left">Credibility</th>
            <th className="px-4 py-2.5 text-right">Results</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.domain} className="border-t border-border/60">
              <td className="px-4 py-2.5 text-ink">{s.source_name ?? "—"}</td>
              <td className="px-4 py-2.5 font-mono text-xs text-ink-dim">{s.domain}</td>
              <td className="px-4 py-2.5"><span className={CRED_BADGE[s.credibility] ?? "badge-mute"}>{s.credibility}</span></td>
              <td className="px-4 py-2.5 text-right font-mono text-ink">{s.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

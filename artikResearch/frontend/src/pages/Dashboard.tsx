import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, Pill, readinessColor } from "../components/ui";

export default function Dashboard({ go }: { go: (p: string, id?: string) => void }) {
  const [d, setD] = useState<any>(null);
  const [agents, setAgents] = useState<any[]>([]);
  const [status, setStatus] = useState<any>(null);

  useEffect(() => {
    api.dashboard().then(setD).catch(() => {});
    api.agents().then((r) => setAgents(r.agents)).catch(() => {});
    api.status().then(setStatus).catch(() => {});
  }, []);

  if (!d) return <div className="text-mut">Loading…</div>;
  const stat = (label: string, val: any, sub?: string, color?: string) => (
    <Card>
      <div className="text-mut text-xs">{label}</div>
      <div className="text-2xl font-bold" style={{ color }}>{val}</div>
      {sub && <div className="text-mut text-xs mt-1">{sub}</div>}
    </Card>
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Dashboard</h1>
        <div className="text-mut text-sm">
          AI providers: {status?.providers?.join(", ") || "none configured"} · {d.journals_learned} journals learned
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {stat("Papers in progress", d.papers_in_progress)}
        {stat("Total papers", d.total_papers)}
        {stat("Avg. readiness", `${d.publication_readiness_avg}%`, undefined, readinessColor(d.publication_readiness_avg))}
        {stat("Papers ready", d.papers_ready, "≥ 85%", "#34d399")}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <div className="font-semibold mb-2">Recently opened papers</div>
          {d.recent_papers?.length ? d.recent_papers.map((p: any) => (
            <div key={p.id} className="flex items-center justify-between py-2 border-b border-line last:border-0 cursor-pointer"
              onClick={() => go("workspace", p.id)}>
              <div className="truncate">{p.name}</div>
              <Pill color={readinessColor(p.readiness)}>{p.readiness != null ? `${p.readiness}%` : p.status}</Pill>
            </div>
          )) : <div className="text-mut text-sm">No papers yet — upload one under My Papers.</div>}
        </Card>
        <Card>
          <div className="font-semibold mb-2">AI recommendations</div>
          {d.recommendations?.map((r: string, i: number) => (
            <div key={i} className="text-sm text-mut py-1">• {r}</div>
          ))}
          <div className="font-semibold mt-3 mb-1">Recent journals</div>
          <div className="text-sm">{d.recent_journals?.join(" · ") || "none learned yet"}</div>
        </Card>
      </div>

      <Card>
        <div className="font-semibold mb-2">AI Agents ({agents.length})</div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-2">
          {agents.map((a) => (
            <div key={a.id} className="flex items-start gap-2 p-2 rounded-lg bg-[#0d1117]">
              <Pill color={a.status === "active" ? "#34d399" : a.status === "partial" ? "#fbbf24" : "#8b949e"}>{a.status}</Pill>
              <div>
                <div className="text-sm font-medium">{a.id}. {a.name}</div>
                <div className="text-mut text-xs">{a.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

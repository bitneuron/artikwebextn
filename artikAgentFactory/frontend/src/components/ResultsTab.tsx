import { useEffect, useState } from "react";
import { resultsApi } from "../api/results";
import { Result } from "../api/types";
import ResultCard from "./ResultCard";

export default function ResultsTab({ agentId, category }: { agentId: number; category?: string }) {
  const [results, setResults] = useState<Result[] | null>(null);
  const [changeStatus, setChangeStatus] = useState("");
  const [savedOnly, setSavedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("relevance_score");

  async function load() {
    const rows = await resultsApi.list(agentId, {
      category, change_status: changeStatus || undefined, is_saved: savedOnly || undefined,
      search: search || undefined, sort, order: "desc",
    });
    setResults(rows);
  }

  useEffect(() => {
    load();
  }, [agentId, category, changeStatus, savedOnly, sort]);

  async function toggleSave(id: number, saved: boolean) {
    await (saved ? resultsApi.save : resultsApi.unsave)(id);
    load();
  }
  async function toggleDismiss(id: number, dismissed: boolean) {
    await (dismissed ? resultsApi.dismiss : resultsApi.undismiss)(id);
    load();
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          className="input max-w-xs" placeholder="Search results…" value={search}
          onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
        />
        <select className="select w-auto" value={changeStatus} onChange={(e) => setChangeStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="new">New</option>
          <option value="changed">Changed</option>
          <option value="unchanged">Unchanged</option>
        </select>
        <select className="select w-auto" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="relevance_score">Sort: Relevance</option>
          <option value="confidence_score">Sort: Confidence</option>
          <option value="created_at">Sort: Recent</option>
        </select>
        <button
          className={savedOnly ? "badge-blue" : "btn-ghost btn-sm"}
          onClick={() => setSavedOnly((s) => !s)}
        >
          {savedOnly ? "★ Saved only" : "☆ Show saved"}
        </button>
        <button className="btn-ghost ml-auto btn-sm" onClick={load}>↻</button>
      </div>

      {results === null && (
        <div className="grid grid-cols-1 gap-3">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton h-28 rounded-2xl" />)}
        </div>
      )}

      {results !== null && results.length === 0 && (
        <div className="card flex flex-col items-center gap-2 p-10 text-center">
          <div className="text-2xl">🛰️</div>
          <h3 className="font-display text-sm font-bold">No results here</h3>
          <p className="max-w-sm text-xs text-ink-dim">Run this agent, or adjust the filters above.</p>
        </div>
      )}

      {results !== null && results.length > 0 && (
        <div className="grid grid-cols-1 gap-3">
          {results.map((r, i) => (
            <ResultCard key={r.id} result={r} index={i} onSave={toggleSave} onDismiss={toggleDismiss} />
          ))}
        </div>
      )}
    </div>
  );
}

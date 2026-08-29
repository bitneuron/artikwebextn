import { useState } from "react";
import RunHistoryTable from "../components/RunHistoryTable";

export default function RunHistory() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <div className="mx-auto max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight text-ink">Run History</h1>
          <p className="mt-1.5 text-sm text-ink-dim">Every run across every agent — scheduled and manual.</p>
        </div>
        <button className="btn-ghost" onClick={() => setRefreshKey((n) => n + 1)}>↻ Refresh</button>
      </div>
      <div className="mt-6">
        <RunHistoryTable key={refreshKey} showAgentLink />
      </div>
    </div>
  );
}

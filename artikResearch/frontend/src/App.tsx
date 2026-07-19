import { useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard";
import Papers from "./pages/Papers";
import Journals from "./pages/Journals";
import Workspace from "./pages/Workspace";
import { Card } from "./components/ui";
import { api } from "./api";

const NAV: [string, string, string][] = [
  ["dashboard", "Dashboard", "🏠"],
  ["papers", "My Papers", "📄"],
  ["journals", "Journal Library", "📚"],
  ["workspace", "Research Workspace", "✍️"],
  ["references", "References", "🔖"],
  ["figures", "Figures", "🖼️"],
  ["templates", "Templates", "🧩"],
  ["agents", "AI Agents", "🤖"],
  ["reviews", "Review History", "🧑‍⚖️"],
  ["submissions", "Submission History", "📤"],
  ["settings", "Settings", "⚙️"],
];

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [paperId, setPaperId] = useState<string | null>(null);

  const go = (p: string, id?: string) => { if (id) setPaperId(id); setPage(p); };

  return (
    <div className="h-screen flex">
      <aside className="w-60 shrink-0 bg-panel border-r border-line flex flex-col">
        <div className="px-4 py-4 border-b border-line">
          <div className="font-bold text-lg">Artik<span className="text-acc">Research</span></div>
          <div className="text-mut text-xs">Publication Copilot</div>
        </div>
        <nav className="p-2 flex-1 overflow-y-auto">
          {NAV.map(([k, label, ic]) => (
            <div key={k} className={`nav-item ${page === k ? "active" : ""}`} onClick={() => setPage(k)}>
              <span>{ic}</span><span>{label}</span>
            </div>
          ))}
        </nav>
        <div className="p-3 text-mut text-xs border-t border-line">Iteration 1 · local</div>
      </aside>

      <main className="flex-1 overflow-y-auto p-5">
        {page === "dashboard" && <Dashboard go={go} />}
        {page === "papers" && <Papers go={go} />}
        {page === "journals" && <Journals />}
        {page === "workspace" && (paperId ? <Workspace paperId={paperId} /> :
          <Placeholder title="Research Workspace" note="Open a paper from My Papers to start the 3-pane workspace." />)}
        {page === "references" && <Placeholder title="References" note="Reference reformatting runs inside the workspace (References tab). Standalone reference manager is on the roadmap." />}
        {page === "figures" && <Placeholder title="Figures" note="Figure/Table agents (resolution, captions, labels) are planned for iteration 2." />}
        {page === "templates" && <Placeholder title="Templates" note="Journal LaTeX/DOCX templates live in journal_library/. Template gallery UI is on the roadmap." />}
        {page === "agents" && <AgentsPage />}
        {page === "reviews" && <Placeholder title="Review History" note="Reviewer-simulation runs are stored per paper (Workspace → Reviewer sim). A cross-paper history view is on the roadmap." />}
        {page === "submissions" && <Placeholder title="Submission History" note="Submission packages are built in the workspace (Build package). Submission tracking is on the roadmap." />}
        {page === "settings" && <SettingsPage />}
      </main>
    </div>
  );
}

function Placeholder({ title, note }: { title: string; note: string }) {
  return <div><h1 className="text-xl font-bold mb-3">{title}</h1><Card><div className="text-mut text-sm">{note}</div></Card></div>;
}

function AgentsPage() {
  const [agents, setAgents] = useState<any[]>([]);
  useEffect(() => { api.agents().then((r) => setAgents(r.agents)).catch(() => {}); }, []);
  return <div><h1 className="text-xl font-bold mb-3">AI Agents</h1>
    <div className="grid md:grid-cols-2 gap-3">
      {agents.map((a) => <Card key={a.id}><div className="flex items-center gap-2">
        <span className="pill" style={{ color: a.status === "active" ? "#34d399" : a.status === "partial" ? "#fbbf24" : "#8b949e", border: "1px solid #333" }}>{a.status}</span>
        <b>{a.id}. {a.name}</b></div><div className="text-mut text-sm mt-1">{a.desc}</div></Card>)}
    </div></div>;
}
function SettingsPage() {
  const [s, setS] = useState<any>(null);
  useEffect(() => { api.status().then(setS).catch(() => {}); }, []);
  return <div><h1 className="text-xl font-bold mb-3">Settings</h1>
    <Card><div className="text-sm space-y-1">
      <div>AI providers: <b>{s?.providers?.join(", ") || "none"}</b></div>
      <div>Reference styles: {s?.reference_styles?.join(", ")}</div>
      <div>Supported journals: {s?.supported_journals?.join(", ")}</div>
    </div></Card></div>;
}

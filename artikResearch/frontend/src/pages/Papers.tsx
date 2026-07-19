import { useEffect, useRef, useState } from "react";
import { api, Paper } from "../api";
import { Card, Pill, readinessColor, statusColor } from "../components/ui";

export default function Papers({ go }: { go: (p: string, id?: string) => void }) {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [journals, setJournals] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const [view, setView] = useState<"list" | "card">("list");
  const [q, setQ] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [target, setTarget] = useState("");
  const [outFmt, setOutFmt] = useState("docx");
  const OUTPUT_FORMATS = ["docx", "pdf", "html", "markdown"];

  const load = () => api.papers().then((r) => setPapers(r.papers)).catch(() => {});
  useEffect(() => {
    load();
    api.journals().then((r) => setJournals([...r.journals.map((j: any) => j.name), ...r.not_yet_learned.map((j: any) => j.name)])).catch(() => {});
  }, []);

  async function upload(f: File) {
    setBusy("Uploading & extracting…");
    const form = new FormData();
    form.append("file", f);
    if (target) form.append("target_journal", target);
    form.append("output_format", outFmt);
    try {
      const p = await api.uploadPaper(form);
      if (p.error) throw new Error(p.error);
      await load();
    } catch (e: any) { alert(e.message); }
    setBusy("");
  }

  const filtered = papers.filter((p) =>
    !q || [p.name, p.target_journal, p.summary].some((x) => (x || "").toLowerCase().includes(q.toLowerCase())));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-bold">My Papers</h1>
        <div className="flex-1" />
        <input className="input max-w-[200px]" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="inline-flex border border-line rounded-lg overflow-hidden">
          <button className={`ghost border-0 rounded-none ${view === "list" ? "bg-acc text-white" : ""}`} onClick={() => setView("list")}>List</button>
          <button className={`ghost border-0 rounded-none ${view === "card" ? "bg-acc text-white" : ""}`} onClick={() => setView("card")}>Cards</button>
        </div>
        <label className="text-mut text-xs flex items-center gap-1">Template
          <select className="input max-w-[190px]" value={target} onChange={(e) => setTarget(e.target.value)} title="Target journal / template to convert to">
            <option value="">None…</option>
            {journals.map((j) => <option key={j}>{j}</option>)}
          </select>
        </label>
        <label className="text-mut text-xs flex items-center gap-1">Output
          <select className="input max-w-[120px]" value={outFmt} onChange={(e) => setOutFmt(e.target.value)} title="Final output file format">
            {OUTPUT_FORMATS.map((f) => <option key={f} value={f}>{f.toUpperCase()}</option>)}
          </select>
        </label>
        <button className="btn" onClick={() => fileRef.current?.click()}>＋ Upload paper</button>
        <input ref={fileRef} type="file" accept=".pdf,.docx,.tex,.md,.txt,.html" className="hidden"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      </div>
      {busy && <div className="text-mut text-sm animate-pulse">⟳ {busy}</div>}
      <div className="text-mut text-xs">Input: PDF · DOCX · LaTeX · Markdown · HTML · text — pick a <b>Template</b> (target journal, e.g. EmergingInvestigators/JEI) and the final <b>Output</b> format (DOCX · PDF · HTML · Markdown).</div>

      {!filtered.length ? (
        <Card><div className="text-mut text-sm">No papers yet. Upload a manuscript to begin the pipeline.</div></Card>
      ) : view === "list" ? (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-mut text-left">
              <th className="py-2">Paper</th><th>Journal</th><th>Status</th><th>Readiness</th><th>Modified</th><th></th>
            </tr></thead>
            <tbody>
              {filtered.map((p) => (
                <tr key={p.id} className="border-t border-line">
                  <td className="py-2 font-medium">{p.name} <span className="text-mut text-xs">.{p.fmt}</span></td>
                  <td>{p.target_journal || "—"}</td>
                  <td><Pill color={statusColor(p.status)}>{p.status}</Pill></td>
                  <td style={{ color: readinessColor(p.readiness) }}>{p.readiness != null ? `${p.readiness}%` : "—"}</td>
                  <td className="text-mut text-xs">{(p.updated_at || "").slice(0, 10)}</td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ghost mr-1" onClick={() => go("workspace", p.id)}>Open</button>
                    <button className="ghost" onClick={async () => { if (confirm(`Delete "${p.name}"?`)) { await api.deletePaper(p.id); load(); } }}>🗑</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((p) => (
            <Card key={p.id} className="cursor-pointer" >
              <div className="flex items-center justify-between">
                <div className="font-semibold truncate">{p.name}</div>
                <Pill color={readinessColor(p.readiness)}>{p.readiness != null ? `${p.readiness}%` : p.status}</Pill>
              </div>
              <div className="text-mut text-xs mt-1">{p.target_journal || "no target journal"}</div>
              <div className="text-sm mt-2 line-clamp-3 min-h-[40px]">{p.summary || "Not yet analyzed."}</div>
              <div className="mt-3"><button className="btn" onClick={() => go("workspace", p.id)}>Open workspace</button></div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

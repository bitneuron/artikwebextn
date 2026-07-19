import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Card, Pill, Ring, ScoreBar, readinessColor } from "../components/ui";

export default function Workspace({ paperId }: { paperId: string }) {
  const [paper, setPaper] = useState<any>(null);
  const [original, setOriginal] = useState("");
  const [manuscript, setManuscript] = useState("");
  const [msgs, setMsgs] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState("");
  const [saved, setSaved] = useState("");
  const [tab, setTab] = useState<"gaps" | "readiness" | "review" | "references" | "package">("readiness");
  const [gaps, setGaps] = useState<any>(null);
  const [readiness, setReadiness] = useState<any>(null);
  const [review, setReview] = useState<any>(null);
  const [refs, setRefs] = useState<any>(null);
  const [pkg, setPkg] = useState<any>(null);
  const chatEnd = useRef<HTMLDivElement>(null);

  async function loadAll() {
    const p = await api.paper(paperId); setPaper(p);
    fetch(`/api/papers/${paperId}/text`).then(r => r.json()).then(d => setOriginal(d.text || "")).catch(() => {});
    api.manuscript(paperId).then(d => setManuscript(d.content || "")).catch(() => {});
    api.chatHistory(paperId).then(d => setMsgs(d.messages || [])).catch(() => {});
  }
  useEffect(() => { loadAll(); }, [paperId]);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const journal = paper?.target_journal || "";

  async function read() {
    setBusy("Reading paper → knowledge graph…");
    try { await api.readPaper(paperId); await loadAll(); } catch (e: any) { alert(e.message); }
    setBusy("");
  }
  async function run(kind: string) {
    setBusy(`Running ${kind}…`);
    try {
      if (kind === "gaps") { setGaps((await api.gaps(paperId, journal)).gaps); setTab("gaps"); }
      if (kind === "readiness") { setReadiness((await api.compliance(paperId, journal)).readiness); setTab("readiness"); await loadAll(); }
      if (kind === "review") { setReview((await api.review(paperId, journal)).review); setTab("review"); }
      if (kind === "references") { setRefs(await api.references(paperId)); setTab("references"); }
      if (kind === "package") { setPkg(await api.buildPackage(paperId, journal)); setTab("package"); }
    } catch (e: any) { alert(e.message); }
    setBusy("");
  }
  async function send() {
    const m = input.trim(); if (!m) return;
    setInput(""); setMsgs([...msgs, { role: "user", content: m }]); setBusy("Thinking…");
    try {
      const d = await api.chat(paperId, m);
      setMsgs((cur) => [...cur, { role: "assistant", content: d.reply }]);
      if (d.updated_manuscript) setManuscript(d.updated_manuscript);
    } catch (e: any) { setMsgs((cur) => [...cur, { role: "assistant", content: "⚠️ " + e.message }]); }
    setBusy("");
  }

  if (!paper) return <div className="text-mut">Loading…</div>;
  const hasKG = !!paper.knowledge;
  const outFmt = paper.output_format || "docx";

  async function setOut(f: string) {
    try { await api.updateSettings(paperId, { output_format: f }); setPaper({ ...paper, output_format: f }); }
    catch (e: any) { alert(e.message); }
  }
  // Convert the manuscript INTO the selected template, write it to generated/, then download.
  async function convertAndExport() {
    if (!journal) { alert("Select a Template (target journal) under My Papers first."); return; }
    setBusy(`Converting to ${journal} template → ${outFmt.toUpperCase()}…`);
    try {
      const d = await api.convert(paperId, journal, outFmt);
      setManuscript(d.manuscript_markdown || manuscript);
      setSaved(`Saved ${d.format.toUpperCase()} → ${d.output_file}`);
      window.open(api.exportUrl(paperId, outFmt), "_blank");
      await loadAll();
    } catch (e: any) { alert(e.message); }
    setBusy("");
  }
  function exportOnly(fmt?: string) { window.open(api.exportUrl(paperId, fmt || outFmt), "_blank"); }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <h1 className="text-lg font-bold">{paper.name}</h1>
        {journal && <Pill color="#60a5fa">Template: {journal}</Pill>}
        {paper.readiness != null && <Pill color={readinessColor(paper.readiness)}>{paper.readiness}% ready</Pill>}
        <div className="flex-1" />
        {!hasKG && <button className="btn" onClick={read}>1 · Read paper</button>}
        {hasKG && <>
          <button className="ghost" onClick={() => run("gaps")}>Gap analysis</button>
          <button className="ghost" onClick={() => run("readiness")}>Readiness</button>
          <button className="ghost" onClick={() => run("review")}>Reviewer sim</button>
          <button className="ghost" onClick={() => run("references")}>References</button>
          <button className="ghost" onClick={() => run("package")}>Build package</button>
          <span className="text-mut text-xs">Output</span>
          <select className="input max-w-[110px]" value={outFmt} onChange={(e) => setOut(e.target.value)}>
            {["docx", "pdf", "html", "markdown"].map((f) => <option key={f} value={f}>{f.toUpperCase()}</option>)}
          </select>
          <button className="btn" onClick={convertAndExport} title="Restructure the paper into the selected journal template, save it to generated/, and download">
            Convert → {outFmt.toUpperCase()}
          </button>
          <button className="ghost" onClick={() => exportOnly()} title="Export the current manuscript as-is (no restructuring)">⬇</button>
        </>}
      </div>
      {saved && <div className="text-xs mb-2" style={{ color: "#34d399" }}>✅ {saved}</div>}
      {busy && <div className="text-mut text-sm animate-pulse mb-2">⟳ {busy}</div>}
      {!hasKG && <Card className="mb-2"><div className="text-mut text-sm">Click <b>Read paper</b> to extract the knowledge graph, then run the pipeline. Set a target journal under My Papers to unlock gap analysis vs. that journal.</div></Card>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 flex-1 min-h-0">
        {/* Left: original */}
        <Card className="flex flex-col min-h-0">
          <div className="font-semibold mb-2 shrink-0">Original paper</div>
          <pre className="text-xs whitespace-pre-wrap overflow-y-auto flex-1 text-mut">{original || "…"}</pre>
        </Card>

        {/* Center: chat */}
        <Card className="flex flex-col min-h-0">
          <div className="font-semibold mb-2 shrink-0">AI Copilot</div>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {msgs.length === 0 && <div className="text-mut text-xs">Try: “Rewrite the abstract to under 250 words”, “Convert references to IEEE”, “Add a Discussion section”, “Suggest a better title”.</div>}
            {msgs.map((m, i) => (
              <div key={i} className={m.role === "user" ? "text-right" : ""}>
                <div className={`inline-block px-3 py-2 rounded-lg text-sm max-w-[92%] text-left ${m.role === "user" ? "bg-acc text-white" : "bg-[#0d1117]"}`}>{m.content}</div>
              </div>
            ))}
            <div ref={chatEnd} />
          </div>
          <div className="flex gap-2 mt-2 shrink-0">
            <input className="input" placeholder="Ask the copilot…" value={input}
              onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} />
            <button className="btn" onClick={send} disabled={!!busy}>Send</button>
          </div>
        </Card>

        {/* Right: generated + analysis tabs */}
        <Card className="flex flex-col min-h-0">
          <div className="flex gap-1 mb-2 shrink-0 flex-wrap text-xs">
            {(["readiness", "gaps", "review", "references", "package"] as const).map((t) => (
              <button key={t} className={`ghost py-1 px-2 ${tab === t ? "bg-acc text-white" : ""}`} onClick={() => setTab(t)}>{t}</button>
            ))}
            <button className={`ghost py-1 px-2 ${tab === ("manuscript" as any) ? "bg-acc text-white" : ""}`} onClick={() => setTab("manuscript" as any)}>manuscript</button>
          </div>
          <div className="flex-1 overflow-y-auto text-sm">
            {tab === "readiness" && (readiness ? <ReadinessView r={readiness} /> : <Empty label="Run Readiness to score this manuscript." />)}
            {tab === "gaps" && (gaps ? <GapsView g={gaps} /> : <Empty label="Run Gap analysis vs. the target journal." />)}
            {tab === "review" && (review ? <ReviewView r={review} /> : <Empty label="Run Reviewer sim for 3 AI reviewers." />)}
            {tab === "references" && (refs ? <RefsView r={refs} /> : <Empty label="Run References to reformat citations." />)}
            {tab === "package" && (pkg ? <PkgView p={pkg} /> : <Empty label="Build package for the submission bundle." />)}
            {(tab as any) === "manuscript" && <pre className="text-xs whitespace-pre-wrap">{manuscript || "No generated version yet — ask the copilot to edit the paper."}</pre>}
          </div>
        </Card>
      </div>
    </div>
  );
}

const Empty = ({ label }: { label: string }) => <div className="text-mut text-xs">{label}</div>;

function ReadinessView({ r }: { r: any }) {
  return (
    <div>
      <div className="flex items-center gap-4 mb-3">
        <Ring value={r.overall} />
        <div>
          <div className="font-semibold">Publication Readiness</div>
          <div className="text-mut text-xs">Acceptance prediction: {r.acceptance_prediction}%</div>
        </div>
      </div>
      {Object.entries(r.dimensions || {}).map(([k, v]: any) => <ScoreBar key={k} label={k.replace(/_/g, " ")} value={v} />)}
      {r.top_actions?.length ? <div className="mt-3"><div className="font-semibold text-xs mb-1">Top actions</div>
        {r.top_actions.map((a: string, i: number) => <div key={i} className="text-xs text-mut py-0.5">• {a}</div>)}</div> : null}
    </div>
  );
}
function GapsView({ g }: { g: any }) {
  const list = (title: string, items: any[]) => items?.length ? (
    <div className="mb-2"><div className="font-semibold text-xs">{title} ({items.length})</div>
      {items.map((x, i) => <div key={i} className="text-xs text-mut py-0.5">• {typeof x === "string" ? x : `${x.rule || x.issue} ${x.severity ? `[${x.severity}]` : ""}`}</div>)}</div>) : null;
  return <div>
    <div className="mb-2"><Pill color="#f87171">{g.gap_count} gaps</Pill></div>
    {list("Missing sections", g.missing_sections)}
    {list("Formatting violations", g.formatting_violations)}
    {list("Missing statements", g.missing_statements)}
    {list("Reference issues", g.reference_issues)}
    {list("Word-count violations", g.word_count_violations)}
    {list("Recommendations", g.recommendations)}
  </div>;
}
function ReviewView({ r }: { r: any }) {
  return <div>
    <div className="flex gap-2 mb-2 text-xs">
      <Pill color="#a78bfa">novelty {r.novelty_score}</Pill>
      <Pill color="#60a5fa">pub {r.publication_score}</Pill>
      <Pill color={readinessColor(r.acceptance_probability)}>accept {r.acceptance_probability}%</Pill>
    </div>
    {r.reviewers?.map((rv: any, i: number) => (
      <div key={i} className="mb-3 p-2 rounded-lg bg-[#0d1117]">
        <div className="flex items-center gap-2"><b className="text-sm">{rv.name}</b><Pill color="#fbbf24">{rv.recommendation}</Pill></div>
        {rv.major_comments?.map((c: string, j: number) => <div key={j} className="text-xs text-mut py-0.5">• {c}</div>)}
      </div>
    ))}
    {r.editor_summary && <div className="text-xs mt-2"><b>Editor:</b> {r.editor_summary}</div>}
  </div>;
}
function RefsView({ r }: { r: any }) {
  return <div>
    <div className="font-semibold text-xs mb-1">{r.style} bibliography</div>
    {r.formatted?.map((f: string, i: number) => <div key={i} className="text-xs py-0.5">{f}</div>)}
    {r.issues?.length ? <div className="mt-2"><div className="font-semibold text-xs">Issues</div>
      {r.issues.map((x: string, i: number) => <div key={i} className="text-xs text-mut py-0.5">⚠ {x}</div>)}</div> : null}
  </div>;
}
function PkgView({ p }: { p: any }) {
  const dl = (name: string, content: string, type = "text/plain") => {
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([content], { type }));
    a.download = name; a.click();
  };
  return <div>
    <div className="font-semibold text-xs mb-1">Export formats</div>
    <div className="flex gap-2 flex-wrap mb-2">
      {Object.entries(p.formats || {}).map(([k, v]: any) => (
        <button key={k} className="ghost text-xs" onClick={() => dl(`manuscript.${k === "markdown" ? "md" : k}`, v)}>⬇ {k}</button>
      ))}
    </div>
    <div className="font-semibold text-xs mb-1">Submission checklist</div>
    {p.submission_checklist?.map((c: any, i: number) => (
      <div key={i} className="text-xs py-0.5">{c.done ? "✅" : "⬜"} {c.item}</div>
    ))}
    <div className="mt-2"><button className="ghost text-xs" onClick={() => dl("cover_letter.txt", p.cover_letter)}>⬇ cover letter</button>
      <button className="ghost text-xs ml-1" onClick={() => dl("reviewer_response.txt", p.reviewer_response_template)}>⬇ reviewer response</button></div>
    <div className="text-mut text-xs mt-2">{p.note}</div>
  </div>;
}

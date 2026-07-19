import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Card, Pill } from "../components/ui";

export default function Journals() {
  const [data, setData] = useState<any>(null);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [sel, setSel] = useState<Record<string, boolean>>({});
  const [cmp, setCmp] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => api.journals().then(setData).catch(() => {});
  useEffect(() => { load(); }, []);

  async function learnText() {
    if (!name.trim() || !text.trim()) { alert("Enter a journal name and paste its instructions."); return; }
    setBusy("Learning journal…");
    try { await api.learnJournalText(name.trim(), text); setText(""); await load(); }
    catch (e: any) { alert(e.message); }
    setBusy("");
  }
  async function uploadDoc(jname: string, f: File) {
    setBusy(`Learning ${jname} from ${f.name}…`);
    const form = new FormData(); form.append("file", f); form.append("kind", "instructions");
    try { const r = await api.uploadJournalDoc(jname, form); if (r.error) throw new Error(r.error); await load(); }
    catch (e: any) { alert(e.message); }
    setBusy("");
  }
  async function compare() {
    const names = Object.keys(sel).filter((k) => sel[k]);
    if (names.length < 2) { alert("Select at least two learned journals."); return; }
    setBusy("Comparing journals…");
    try { setCmp(await api.compareJournals(names)); } catch (e: any) { alert(e.message); }
    setBusy("");
  }

  if (!data) return <div className="text-mut">Loading…</div>;
  const learned = data.journals as any[];

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Journal Library</h1>
      {busy && <div className="text-mut text-sm animate-pulse">⟳ {busy}</div>}

      <Card>
        <div className="font-semibold mb-2">Teach a journal</div>
        <div className="text-mut text-xs mb-2">Upload the author instructions / formatting guide / submission checklist — or paste the text. The AI learns the requirements automatically.</div>
        <div className="flex gap-2 flex-wrap items-center">
          <input className="input max-w-[220px]" placeholder="Journal name (e.g. Nature)" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="ghost" onClick={() => { if (!name.trim()) { alert("Enter a journal name first."); return; } fileRef.current?.click(); }}>Upload instructions file</button>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.html,.tex,.md,.txt" className="hidden"
            onChange={(e) => e.target.files?.[0] && uploadDoc(name.trim() || "Custom", e.target.files[0])} />
        </div>
        <textarea className="input mt-2 h-24" placeholder="…or paste the author instructions text here" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="mt-2"><button className="btn" onClick={learnText}>Learn from text</button></div>
      </Card>

      <div className="flex items-center gap-2">
        <div className="font-semibold">Learned journals ({learned.length})</div>
        <div className="flex-1" />
        <button className="ghost" onClick={compare}>Compare selected</button>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
        {learned.map((j) => (
          <Card key={j.name}>
            <div className="flex items-center gap-2">
              <input type="checkbox" checked={!!sel[j.name]} onChange={(e) => setSel({ ...sel, [j.name]: e.target.checked })} />
              <div className="font-semibold flex-1">{j.name}</div>
              <Pill color="#34d399">{j.source}</Pill>
            </div>
            <div className="text-xs text-mut mt-2 space-y-1">
              <div>Reference style: <b className="text-txt">{j.profile.reference_style || "—"}</b></div>
              <div>Abstract limit: {j.profile.word_limits?.abstract ?? "—"} · Max refs: {j.profile.max_references ?? "—"}</div>
              <div>Required sections: {(j.profile.required_sections || []).length}</div>
            </div>
            <button className="ghost mt-2" onClick={() => setDetail(j)}>View profile</button>
          </Card>
        ))}
        {data.not_yet_learned.map((j: any) => (
          <Card key={j.name} className="opacity-60">
            <div className="font-semibold">{j.name}</div>
            <div className="text-xs text-mut mt-1">Supported — upload its instructions to learn it.</div>
          </Card>
        ))}
      </div>

      {cmp && (
        <Card>
          <div className="font-semibold mb-2">Comparison</div>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <tbody>
              {cmp.comparison?.map((row: any, i: number) => (
                <tr key={i} className="border-t border-line">
                  <td className="py-1 text-mut w-40">{row.dimension}</td>
                  {Object.entries(row.values || {}).map(([k, v]: any) => <td key={k} className="py-1 px-2">{String(v)}</td>)}
                </tr>
              ))}
            </tbody>
          </table></div>
          <div className="text-sm mt-2"><b>Recommendation:</b> {cmp.recommendation}</div>
          <button className="ghost mt-2" onClick={() => setCmp(null)}>Close</button>
        </Card>
      )}

      {detail && (
        <div className="fixed inset-0 bg-black/60 grid place-items-center p-4 z-50" onClick={() => setDetail(null)}>
          <Card className="max-w-2xl w-full max-h-[85vh] overflow-y-auto" >
            <div className="flex items-center"><div className="font-semibold flex-1">{detail.name} — learned profile</div>
              <button className="ghost" onClick={() => setDetail(null)}>✕</button></div>
            <pre className="text-xs mt-2 whitespace-pre-wrap">{JSON.stringify(detail.profile, null, 2)}</pre>
          </Card>
        </div>
      )}
    </div>
  );
}

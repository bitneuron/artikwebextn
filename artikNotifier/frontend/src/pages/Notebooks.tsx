import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

interface Notebook {
  id: number; name: string; icon: string | null; color: string | null;
  description: string | null; is_favorite: boolean; is_archived: boolean;
  is_default: boolean; note_count: number;
}

const ICONS = ["📓", "💰", "🏥", "📁", "🏠", "🎓", "🔬", "✈️", "🔑", "💡", "📅", "🍳", "⏰", "📝"];

export default function Notebooks() {
  const nav = useNavigate();
  const [items, setItems] = useState<Notebook[]>([]);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("📓");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const flash = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2000); };
  const load = async () => setItems(await api.get<Notebook[]>("/api/notebooks"));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try { await api.post("/api/notebooks", { name: name.trim(), icon }); setName(""); flash("Notebook created"); await load(); }
    finally { setBusy(false); }
  };
  const toggleFav = async (nb: Notebook) => { await api.put(`/api/notebooks/${nb.id}`, { is_favorite: !nb.is_favorite }); await load(); };
  const rename = async (nb: Notebook) => {
    const nn = prompt("Rename notebook", nb.name);
    if (nn && nn.trim()) { await api.put(`/api/notebooks/${nb.id}`, { name: nn.trim() }); await load(); }
  };
  const remove = async (nb: Notebook) => {
    if (nb.is_default) { flash("Can't delete the default notebook"); return; }
    if (!confirm(`Delete "${nb.name}"? Its notes move to your default notebook.`)) return;
    await api.del(`/api/notebooks/${nb.id}`); flash("Notebook deleted"); await load();
  };

  return (
    <div className="space-y-6">
      <div className="card p-4">
        <h2 className="text-lg font-semibold mb-3">📚 New Notebook</h2>
        <div className="flex flex-wrap gap-2 items-center">
          <select className="input !w-20" value={icon} onChange={(e) => setIcon(e.target.value)}>
            {ICONS.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
          <input className="input flex-1 min-w-[220px]" placeholder="Notebook name (e.g. Finance, Medical, Projects)"
            value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()} />
          <button className="btn-primary" disabled={busy} onClick={create}>Create</button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((nb) => (
          <div key={nb.id} className="card p-4 cursor-pointer transition hover:shadow-lg"
            onClick={() => nav(`/notes?notebook_id=${nb.id}`)}>
            <div className="flex items-start justify-between">
              <div className="text-2xl">{nb.icon || "📓"}</div>
              <button className="text-lg leading-none" title="Favorite"
                onClick={(e) => { e.stopPropagation(); toggleFav(nb); }}>{nb.is_favorite ? "★" : "☆"}</button>
            </div>
            <div className="mt-2 font-semibold">
              {nb.name} {nb.is_default && <span className="text-xs opacity-60">· default</span>}
            </div>
            <div className="text-sm opacity-70">{nb.note_count} note{nb.note_count === 1 ? "" : "s"}</div>
            <div className="mt-3 flex gap-2 text-sm">
              <button className="btn-ghost !px-2 !py-1" onClick={(e) => { e.stopPropagation(); rename(nb); }}>Rename</button>
              {!nb.is_default && <button className="btn-ghost !px-2 !py-1" onClick={(e) => { e.stopPropagation(); remove(nb); }}>Delete</button>}
            </div>
          </div>
        ))}
        {items.length === 0 && <div className="opacity-70 text-sm">No notebooks yet — create one above.</div>}
      </div>

      {toast && <div className="fixed bottom-4 right-4 card px-4 py-2 shadow-lg">{toast}</div>}
    </div>
  );
}

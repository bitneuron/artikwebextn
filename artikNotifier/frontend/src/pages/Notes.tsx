import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { QuickNote } from "../api/types";

interface Notebook { id: number; name: string; icon: string | null; is_default: boolean; }

const REPEATS = [["", "No repeat"], ["daily", "Daily"], ["weekly", "Weekly"], ["monthly", "Monthly"], ["yearly", "Yearly"]];

function fmtDate(s: string): string {
  return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function Notes() {
  const [params] = useSearchParams();
  const notebookFilter = params.get("notebook_id") || "";

  const [notes, setNotes] = useState<QuickNote[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [tab, setTab] = useState<"notes" | "reminders">("notes");
  const [search, setSearch] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [reminderOpen, setReminderOpen] = useState(false);

  const selected = notes.find((n) => n.id === selectedId) || null;
  const allTags = useMemo(() => Array.from(new Set(notes.flatMap((n) => n.tags))).sort(), [notes]);

  async function load(keepSel = true) {
    const p = new URLSearchParams();
    if (search) p.set("search", search);
    if (notebookFilter) p.set("notebook_id", notebookFilter);
    if (tab === "reminders") p.set("has_reminder", "true");
    if (tagFilter) p.set("tag", tagFilter);
    p.set("sort", "updated_at"); p.set("order", "desc"); p.set("limit", "200");
    const rows = await api.get<QuickNote[]>(`/api/notes?${p.toString()}`);
    setNotes(rows);
    if (!keepSel || !rows.find((n) => n.id === selectedId)) setSelectedId(rows[0]?.id ?? null);
  }
  useEffect(() => { load(false); /* eslint-disable-next-line */ }, [search, notebookFilter, tab, tagFilter]);
  useEffect(() => { api.get<Notebook[]>("/api/notebooks").then(setNotebooks); }, []);

  // ── editor draft + debounced autosave ─────────────────────────────────────
  const [draft, setDraft] = useState({ title: "", note_text: "" });
  useEffect(() => {
    if (selected) setDraft({ title: selected.title ?? "", note_text: selected.note_text });
    else setDraft({ title: "", note_text: "" });
    setReminderOpen(false);
    // eslint-disable-next-line
  }, [selectedId]);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  function patch(body: Record<string, unknown>, debounce = 0) {
    if (!selected) return;
    const id = selected.id;
    const run = async () => {
      setSaving(true);
      try {
        const upd = await api.put<QuickNote>(`/api/notes/${id}`, body);
        setNotes((ns) => ns.map((n) => (n.id === id ? upd : n)));
      } finally { setSaving(false); }
    };
    if (timer.current) clearTimeout(timer.current);
    if (debounce) timer.current = setTimeout(run, debounce);
    else run();
  }
  const onTitle = (v: string) => { setDraft((d) => ({ ...d, title: v })); patch({ title: v || null }, 600); };
  const onBody = (v: string) => { setDraft((d) => ({ ...d, note_text: v })); patch({ note_text: v || " " }, 600); };

  async function newNote() {
    const body: Record<string, unknown> = { note_text: " ", title: "" };
    if (notebookFilter) body.notebook_id = Number(notebookFilter);
    const n = await api.post<QuickNote>("/api/notes", body);
    await load();
    setSelectedId(n.id);
  }
  async function del() {
    if (!selected || !confirm("Delete this note?")) return;
    const id = selected.id;
    await api.del(`/api/notes/${id}`);
    setNotes((ns) => { const rest = ns.filter((n) => n.id !== id); setSelectedId(rest[0]?.id ?? null); return rest; });
  }
  function addTag(t: string) { if (selected && t.trim()) patch({ tags: [...new Set([...selected.tags, t.trim()])] }); }
  function removeTag(t: string) { if (selected) patch({ tags: selected.tags.filter((x) => x !== t) }); }

  const nbName = (id: number | null) => notebooks.find((n) => n.id === id)?.name || "Notebook";

  return (
    <div className="-m-4 md:-m-6 flex h-[calc(100vh-3.5rem)]">
      {/* ── LIST PANE ─────────────────────────────────────────────── */}
      <aside className="flex w-[340px] shrink-0 flex-col border-r border-slate-200 dark:border-slate-800">
        <div className="space-y-3 border-b border-slate-200 p-3 dark:border-slate-800">
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-2.5 opacity-40">🔍</span>
            <input className="input w-full !pl-9" placeholder="Search" value={search}
              onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="flex items-baseline gap-2">
            <h1 className="text-2xl font-bold">{tab === "reminders" ? "Reminders" : "Notes"}</h1>
            <span className="text-sm opacity-40">{notes.length}</span>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex gap-1">
              <button onClick={() => setTab("notes")}
                className={`rounded-full px-3 py-1 text-sm ${tab === "notes" ? "bg-slate-200 font-medium dark:bg-slate-700" : "opacity-60"}`}>Notes</button>
              <button onClick={() => setTab("reminders")}
                className={`rounded-full px-3 py-1 text-sm ${tab === "reminders" ? "bg-slate-200 font-medium dark:bg-slate-700" : "opacity-60"}`}>Reminders</button>
            </div>
            <div className="flex items-center gap-3 text-lg">
              <button title="New note" onClick={newNote}>🖉</button>
              <div className="relative">
                <button title="Filter" onClick={() => setFilterOpen((o) => !o)}>⚑</button>
                {filterOpen && (
                  <div className="absolute right-0 z-30 mt-2 w-60 rounded-xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-[#0d1117]">
                    <div className="mb-1 px-2 text-xs font-semibold opacity-60">🏷 Filter by tag</div>
                    <button onClick={() => { setTagFilter(""); setFilterOpen(false); }}
                      className={`block w-full rounded px-2 py-1 text-left text-sm ${!tagFilter ? "bg-slate-100 dark:bg-slate-800" : ""}`}>All notes</button>
                    <div className="max-h-52 overflow-y-auto">
                      {allTags.map((t) => (
                        <label key={t} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                          <input type="checkbox" checked={tagFilter === t}
                            onChange={() => { setTagFilter(tagFilter === t ? "" : t); setFilterOpen(false); }} />{t}
                        </label>
                      ))}
                      {allTags.length === 0 && <div className="px-2 py-1 text-xs opacity-50">No tags yet</div>}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {notes.map((n) => (
            <button key={n.id} onClick={() => setSelectedId(n.id)}
              className={`block w-full border-b border-slate-100 px-4 py-3 text-left dark:border-slate-800 ${selectedId === n.id ? "bg-brand/5 border-l-2 border-l-brand" : "hover:bg-slate-50 dark:hover:bg-slate-800/50"}`}>
              <div className="truncate font-semibold">{n.title || n.note_text.trim().slice(0, 40) || "Untitled"}</div>
              <div className="mt-0.5 line-clamp-2 text-sm opacity-60">{n.note_text.trim().slice(0, 140)}</div>
              <div className="mt-1 flex items-center gap-2 text-xs opacity-40">
                <span>{fmtDate(n.updated_at)}</span>
                {n.due_date && <span title="Has reminder">⏰</span>}
                {n.is_favorite && <span className="text-amber-500">★</span>}
                {n.tags.slice(0, 2).map((t) => <span key={t} className="rounded bg-slate-100 px-1 dark:bg-slate-800">#{t}</span>)}
              </div>
            </button>
          ))}
          {notes.length === 0 && <div className="p-6 text-sm opacity-60">No notes here. Click 🖉 to create one.</div>}
        </div>
      </aside>

      {/* ── EDITOR PANE ───────────────────────────────────────────── */}
      <section className="flex-1 overflow-y-auto">
        {selected ? (
          <div className="mx-auto max-w-3xl px-8 py-6">
            <div className="mb-2 flex items-center justify-between text-sm opacity-60">
              <div className="truncate">📓 {nbName(selected.notebook_id)} <span className="opacity-40">›</span> {selected.title || "Untitled"}</div>
              <div className="flex items-center gap-3">
                {saving && <span className="text-xs opacity-50">Saving…</span>}
                <div className="relative">
                  <button title="Reminder" onClick={() => setReminderOpen((o) => !o)}
                    className={selected.due_date ? "text-brand" : ""}>⏰</button>
                  {reminderOpen && (
                    <>
                      <div className="fixed inset-0 z-20" onClick={() => setReminderOpen(false)} />
                      <div className="absolute right-0 top-full z-30 mt-2 w-80 rounded-xl border border-slate-200 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-[#0d1117]">
                        <div className="mb-3 flex items-center justify-between">
                          <span className="font-medium opacity-80">⏰ Reminder</span>
                          {selected.due_date && (
                            <button className="text-xs text-red-500"
                              onClick={() => patch({ due_date: null, due_time: null, repeat: null })}>Clear</button>
                          )}
                        </div>
                        <input className="input mb-2 w-full" type="date" value={selected.due_date || ""}
                          onChange={(e) => patch({ due_date: e.target.value || null })} />
                        <input className="input mb-2 w-full" type="time" value={selected.due_time || ""}
                          onChange={(e) => patch({ due_time: e.target.value || null })} />
                        <select className="input mb-2 w-full" value={selected.repeat || ""}
                          onChange={(e) => patch({ repeat: e.target.value || null })}>
                          {REPEATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                        <select className="input w-full" value={selected.notebook_id ?? ""}
                          onChange={(e) => patch({ notebook_id: e.target.value ? Number(e.target.value) : null })}
                          title="Move to notebook">
                          {notebooks.map((nb) => <option key={nb.id} value={nb.id}>{(nb.icon || "📓") + " " + nb.name}</option>)}
                        </select>
                      </div>
                    </>
                  )}
                </div>
                <button title="Favorite" onClick={() => patch({ is_favorite: !selected.is_favorite })}>{selected.is_favorite ? "★" : "☆"}</button>
                <button title="Delete" onClick={del}>🗑</button>
              </div>
            </div>
            <div className="mb-4 text-xs opacity-40">Edited {fmtDate(selected.updated_at)}</div>

            <input className="mb-3 w-full bg-transparent text-3xl font-bold outline-none placeholder:opacity-30"
              placeholder="Title" value={draft.title} onChange={(e) => onTitle(e.target.value)} />

            {/* tags */}
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {selected.tags.map((t) => (
                <span key={t} className="flex items-center gap-1 rounded-full bg-slate-200 px-2 py-0.5 text-xs dark:bg-slate-700">
                  🏷 {t}<button className="opacity-60 hover:opacity-100" onClick={() => removeTag(t)}>×</button>
                </span>
              ))}
              <input className="w-24 border-b border-dashed border-slate-400 bg-transparent text-xs outline-none"
                placeholder="+ add tag"
                onKeyDown={(e) => { if (e.key === "Enter") { addTag((e.target as HTMLInputElement).value); (e.target as HTMLInputElement).value = ""; } }} />
            </div>

            {selected.due_date && (
              <div className="mb-4 inline-flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-1 text-sm dark:bg-slate-800/60">
                <span className="opacity-70">⏰ {selected.due_date}{selected.due_time ? ` · ${selected.due_time}` : ""}
                  {selected.repeat ? ` · ${selected.repeat}` : ""}</span>
                <button className="opacity-50 hover:opacity-100" onClick={() => setReminderOpen(true)}>edit</button>
              </div>
            )}

            <textarea className="min-h-[55vh] w-full resize-none bg-transparent text-base leading-relaxed outline-none placeholder:opacity-30"
              placeholder="Start writing…" value={draft.note_text} onChange={(e) => onBody(e.target.value)} />
          </div>
        ) : (
          <div className="grid h-full place-items-center text-center opacity-50">
            <div><div className="mb-2 text-4xl">📝</div>Select a note, or click 🖉 to create one.</div>
          </div>
        )}
      </section>
    </div>
  );
}

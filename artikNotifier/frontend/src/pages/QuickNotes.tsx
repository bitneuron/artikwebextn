import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { NoteOptions, QuickNote } from "../api/types";

interface Notebook { id: number; name: string; icon: string | null; is_default: boolean; }

const EMPTY_FORM = { title: "", note_text: "", category: "Personal", priority: "medium",
  due_date: "", due_time: "", tags: "", notebook_id: "", repeat: "", is_favorite: false };

type Form = typeof EMPTY_FORM;

function tagsToArray(s: string): string[] {
  return s.split(",").map((t) => t.trim()).filter(Boolean);
}

function payloadFrom(f: Form) {
  return {
    title: f.title || null,
    note_text: f.note_text.trim(),
    category: f.category,
    priority: f.priority,
    due_date: f.due_date || null,
    due_time: f.due_time || null,
    tags: tagsToArray(f.tags),
    notebook_id: f.notebook_id ? Number(f.notebook_id) : null,
    repeat: f.repeat || null,
    is_favorite: f.is_favorite,
  };
}

const STATUS_BADGE: Record<string, string> = {
  active: "bg-brand/10 text-brand",
  completed: "bg-emerald-500/10 text-emerald-500",
  archived: "bg-slate-500/10 text-slate-400",
};

export default function QuickNotes() {
  const [items, setItems] = useState<QuickNote[]>([]);
  const [options, setOptions] = useState<NoteOptions | null>(null);
  const [q, setQ] = useState({ status: "", category: "", priority: "", tag: "", search: "",
    sort: "created_at", order: "desc" });
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState<QuickNote | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const captureRef = useRef<HTMLTextAreaElement>(null);
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const notebookFilter = searchParams.get("notebook_id") || "";
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const activeNotebook = notebooks.find((n) => String(n.id) === notebookFilter);

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(null), 3000); }

  async function load() {
    const params = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v && params.set(k, v));
    if (notebookFilter) params.set("notebook_id", notebookFilter);
    setItems(await api.get<QuickNote[]>(`/api/notes?${params.toString()}`));
  }
  useEffect(() => { api.get<NoteOptions>("/api/notes/options").then(setOptions); }, []);
  useEffect(() => { api.get<Notebook[]>("/api/notebooks").then(setNotebooks); }, []);
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [notebookFilter]);
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [q]);

  async function create(e?: React.FormEvent) {
    e?.preventDefault();
    if (!form.note_text.trim()) { captureRef.current?.focus(); return; }
    setBusy(true);
    try {
      await api.post("/api/notes", payloadFrom(form));
      setForm(EMPTY_FORM); setExpanded(false); flash("Note saved");
      await load();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "Could not save note");
    } finally { setBusy(false); }
  }

  async function act(path: string, ok: string) {
    try { await api.post(path); flash(ok); await load(); }
    catch (err) { flash(err instanceof ApiError ? err.message : "Action failed"); }
  }
  async function del(n: QuickNote) {
    if (!confirm("Delete this note?")) return;
    try { await api.del(`/api/notes/${n.id}`); flash("Note deleted"); await load(); }
    catch { flash("Delete failed"); }
  }
  async function convert(n: QuickNote) {
    try {
      const r = await api.post<{ reminder_id: number }>(`/api/notes/${n.id}/convert`);
      flash("Converted to reminder");
      await load();
      if (confirm("Reminder created. Open it now?")) nav(`/reminders/${r.reminder_id}`);
    } catch (err) { flash(err instanceof ApiError ? err.message : "Convert failed"); }
  }

  function focusCapture() { setExpanded(true); setTimeout(() => captureRef.current?.focus(), 50); }

  return (
    <div className="space-y-4 pb-20">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">📝 Quick Notes</h1>
        <span className="text-xs text-slate-400">{items.length} note{items.length === 1 ? "" : "s"}</span>
      </div>

      {/* ── Quick capture ─────────────────────────────────────────────── */}
      <form onSubmit={create} className="card space-y-2">
        <div className="flex gap-2">
          <textarea
            ref={captureRef}
            className="input min-h-[44px] flex-1 resize-y"
            rows={expanded ? 3 : 1}
            placeholder="Capture a thought, todo, idea… (required)"
            value={form.note_text}
            onChange={(e) => setForm({ ...form, note_text: e.target.value })}
            onFocus={() => setExpanded(true)}
            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") create(); }}
          />
          <button type="submit" className="btn-primary self-start whitespace-nowrap" disabled={busy}>
            {busy ? "Saving…" : "+ Save"}
          </button>
        </div>
        {expanded && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <input className="input col-span-2 sm:col-span-3 lg:col-span-2" placeholder="Title (optional)"
              value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <select className="input" value={form.notebook_id || notebookFilter}
              onChange={(e) => setForm({ ...form, notebook_id: e.target.value })} title="Notebook">
              <option value="">📓 Notebook…</option>
              {notebooks.map((nb) => <option key={nb.id} value={nb.id}>{(nb.icon || "📓") + " " + nb.name}</option>)}
            </select>
            <select className="input" value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {options?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select className="input" value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {options?.priorities.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <input className="input" type="date" value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            <input className="input" type="time" value={form.due_time}
              onChange={(e) => setForm({ ...form, due_time: e.target.value })} />
            <select className="input" value={form.repeat}
              onChange={(e) => setForm({ ...form, repeat: e.target.value })} title="Repeat">
              <option value="">No repeat</option>
              <option value="daily">Daily</option><option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option><option value="yearly">Yearly</option>
            </select>
            <input className="input col-span-2 sm:col-span-3 lg:col-span-5" placeholder="Tags (comma separated)"
              value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
          </div>
        )}
      </form>

      {/* ── Filters ───────────────────────────────────────────────────── */}
      <div className="card grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <input className="input col-span-2" placeholder="Search notes, tags… (try tag:finance)"
          value={q.search} onChange={(e) => setQ({ ...q, search: e.target.value })} />
        <select className="input" value={q.status} onChange={(e) => setQ({ ...q, status: e.target.value })}>
          <option value="">All status</option>
          {["active", "completed", "archived"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="input" value={q.category} onChange={(e) => setQ({ ...q, category: e.target.value })}>
          <option value="">All categories</option>
          {options?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="input" value={q.priority} onChange={(e) => setQ({ ...q, priority: e.target.value })}>
          <option value="">All priorities</option>
          {options?.priorities.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="input" value={`${q.sort}:${q.order}`}
          onChange={(e) => { const [sort, order] = e.target.value.split(":"); setQ({ ...q, sort, order }); }}>
          <option value="created_at:desc">Newest</option>
          <option value="created_at:asc">Oldest</option>
          <option value="due_date:asc">Due date</option>
          <option value="updated_at:desc">Recently updated</option>
          <option value="title:asc">Alphabetical</option>
        </select>
      </div>

      {/* ── List ──────────────────────────────────────────────────────── */}
      {items.length === 0 ? (
        <p className="card text-center text-slate-400">
          No notes yet. <button className="text-brand" onClick={focusCapture}>Capture one →</button>
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((n) => (
            <div key={n.id} className="card flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  {n.title && <div className="truncate font-semibold">{n.title}</div>}
                  <p className="whitespace-pre-wrap break-words text-sm text-slate-600 dark:text-slate-300">
                    {n.note_text.length > 240 ? n.note_text.slice(0, 240) + "…" : n.note_text}
                  </p>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${STATUS_BADGE[n.status] || ""}`}>
                  {n.status}
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">{n.category}</span>
                {n.tags.map((t) => <span key={t} className="rounded bg-brand/10 px-1.5 py-0.5 text-brand">#{t}</span>)}
                {n.due_date && <span>· due {n.due_date}{n.due_time ? ` ${n.due_time}` : ""}</span>}
                {n.reminder_id && <span className="text-emerald-500">· ⏰ reminder</span>}
              </div>

              {n.due_date && !n.reminder_id && n.status === "active" && (
                <button onClick={() => convert(n)}
                  className="rounded-lg bg-amber-500/10 px-2 py-1 text-left text-xs text-amber-600 dark:text-amber-400">
                  This note has a due date — convert it into a reminder?
                </button>
              )}

              <div className="mt-auto flex flex-wrap gap-1.5 pt-1 text-xs">
                <button className="btn-ghost !px-2 !py-1" onClick={() => setEditing(n)}>Edit</button>
                {n.status === "active" && (
                  <button className="btn-ghost !px-2 !py-1" onClick={() => act(`/api/notes/${n.id}/complete`, "Completed")}>Complete</button>
                )}
                {!n.reminder_id && n.status !== "archived" && (
                  <button className="btn-ghost !px-2 !py-1" onClick={() => convert(n)}>Convert</button>
                )}
                {n.status === "archived"
                  ? <button className="btn-ghost !px-2 !py-1" onClick={() => act(`/api/notes/${n.id}/restore`, "Restored")}>Restore</button>
                  : <button className="btn-ghost !px-2 !py-1" onClick={() => act(`/api/notes/${n.id}/archive`, "Archived")}>Archive</button>}
                <button className="btn-ghost !px-2 !py-1 text-red-500" onClick={() => del(n)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Mobile floating capture button ────────────────────────────── */}
      <button onClick={focusCapture} aria-label="New quick note"
        className="btn-primary fixed bottom-6 right-6 z-30 h-14 w-14 rounded-full text-2xl shadow-lg sm:hidden">
        +
      </button>

      {editing && (
        <EditModal note={editing} options={options} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); flash("Note updated"); }} />
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-slate-900 px-4 py-2 text-sm text-white shadow-lg dark:bg-slate-700">
          {toast}
        </div>
      )}
    </div>
  );
}

function EditModal({ note, options, onClose, onSaved }: {
  note: QuickNote; options: NoteOptions | null; onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState<Form>({
    title: note.title ?? "", note_text: note.note_text, category: note.category,
    priority: note.priority, due_date: note.due_date ?? "", due_time: note.due_time ?? "",
    tags: note.tags.join(", "),
    notebook_id: note.notebook_id ? String(note.notebook_id) : "",
    repeat: note.repeat ?? "", is_favorite: note.is_favorite ?? false,
  });
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  useEffect(() => { api.get<Notebook[]>("/api/notebooks").then(setNotebooks); }, []);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try { await api.put(`/api/notes/${note.id}`, payloadFrom(f)); onSaved(); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <form onClick={(e) => e.stopPropagation()} onSubmit={save}
        className="w-full max-w-lg space-y-3 rounded-2xl bg-white p-5 dark:bg-[#0d1117]">
        <h2 className="text-lg font-bold">Edit note</h2>
        <input className="input w-full" placeholder="Title (optional)" value={f.title}
          onChange={(e) => setF({ ...f, title: e.target.value })} />
        <textarea className="input min-h-[120px] w-full" value={f.note_text}
          onChange={(e) => setF({ ...f, note_text: e.target.value })} required />
        <div className="grid grid-cols-2 gap-2">
          <select className="input col-span-2" value={f.notebook_id}
            onChange={(e) => setF({ ...f, notebook_id: e.target.value })} title="Notebook">
            <option value="">📓 Notebook…</option>
            {notebooks.map((nb) => <option key={nb.id} value={nb.id}>{(nb.icon || "📓") + " " + nb.name}</option>)}
          </select>
          <select className="input" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            {options?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="input" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
            {options?.priorities.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <input className="input" type="date" value={f.due_date}
            onChange={(e) => setF({ ...f, due_date: e.target.value })} />
          <input className="input" type="time" value={f.due_time}
            onChange={(e) => setF({ ...f, due_time: e.target.value })} />
          <select className="input col-span-2" value={f.repeat}
            onChange={(e) => setF({ ...f, repeat: e.target.value })} title="Repeat reminder">
            <option value="">No repeat</option>
            <option value="daily">Daily</option><option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option><option value="yearly">Yearly</option>
          </select>
          <label className="col-span-2 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.is_favorite}
              onChange={(e) => setF({ ...f, is_favorite: e.target.checked })} /> ⭐ Favorite
          </label>
        </div>
        <input className="input w-full" placeholder="Tags (comma separated)" value={f.tags}
          onChange={(e) => setF({ ...f, tags: e.target.value })} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </div>
  );
}

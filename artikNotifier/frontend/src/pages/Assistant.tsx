import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ChatMessage, ChatResponse } from "../api/types";

const SUGGESTIONS = [
  "What reminders are coming this week?",
  "Do I have any overdue payments?",
  "Which notifications are unread?",
  "How should I improve my reminder settings?",
  "Show me finance-related reminders",
  "Show my finance notes",
  "What notes are due this week?",
  "Summarize my calendar for this month",
];

export default function Assistant() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [insights, setInsights] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  async function load() {
    const [hist, ins] = await Promise.all([
      api.get<ChatMessage[]>("/api/assistant/history"),
      api.get<string[]>("/api/assistant/insights"),
    ]);
    setMessages(hist);
    setInsights(ins);
  }
  useEffect(() => { load(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function send(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || busy) return;
    setBusy(true);
    // optimistic echo (React escapes content → safe from XSS)
    setMessages((m) => [...m, { id: Date.now(), role: "user", content: msg, created_at: "" }]);
    setInput("");
    try {
      const r = await api.post<ChatResponse>("/api/assistant/chat", { message: msg });
      setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant", content: r.reply, created_at: "" }]);
      setInsights(r.insights);
    } catch {
      setMessages((m) => [...m, { id: Date.now() + 2, role: "assistant", content: "Sorry, something went wrong.", created_at: "" }]);
    } finally { setBusy(false); }
  }

  async function clearHistory() {
    await api.del("/api/assistant/history");
    setMessages([]);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">🤖 Ask Artik Assistant</h1>
        {messages.length > 0 && <button className="btn-ghost !py-1.5" onClick={clearHistory}>Clear chat</button>}
      </div>

      {insights.length > 0 && (
        <div className="card">
          <div className="mb-2 text-sm font-semibold text-slate-500">💡 Insights</div>
          <div className="space-y-1.5">
            {insights.map((i, k) => (
              <div key={k} className="flex gap-2 text-sm"><span>•</span><span>{i}</span></div>
            ))}
          </div>
        </div>
      )}

      <div className="card flex min-h-[320px] flex-1 flex-col gap-3">
        {messages.length === 0 && (
          <div className="my-auto text-center text-sm text-slate-400">
            Ask me about your reminders, notifications, and settings. I only ever see <b>your</b> data.
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
              m.role === "user"
                ? "bg-brand text-white"
                : "bg-slate-100 dark:bg-slate-800"
            }`}>
              {/* React escapes text → stored-XSS safe */}
              {m.content}
            </div>
          </div>
        ))}
        {busy && <div className="text-sm text-slate-400">Artik Assistant is thinking…</div>}
        <div ref={endRef} />
      </div>

      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="badge cursor-pointer border border-slate-300 px-3 py-1 text-xs dark:border-slate-700 hover:border-brand"
            onClick={() => send(s)}>{s}</button>
        ))}
      </div>

      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <input className="input flex-1" placeholder="Ask Artik Assistant…" value={input}
          onChange={(e) => setInput(e.target.value)} maxLength={1000} />
        <button className="btn-primary" disabled={busy || !input.trim()}>Send</button>
      </form>
    </div>
  );
}

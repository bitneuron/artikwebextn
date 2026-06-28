import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { APPS, CURRENT_APP } from "../platform/apps";

// Global product switcher — jump between Artik apps from any page. Built from the
// app registry so new products appear automatically. SSO-ready: cross-app links go
// to each product's deployment; when a shared identity provider is added, the bearer
// token can be forwarded here without changing callers.
export default function AppSwitcher() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const nav = useNavigate();

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const go = (url: string, current?: boolean) => {
    setOpen(false);
    if (current || url === "/") nav("/");
    else window.location.href = url;
  };

  return (
    <div className="relative" ref={ref}>
      <button
        className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm font-semibold hover:bg-slate-100 dark:hover:bg-slate-800"
        title="Switch Artik app"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{CURRENT_APP.icon}</span>
        <span className="hidden sm:inline">Artik <span className="text-brand">{CURRENT_APP.short}</span></span>
        <span className="text-xs text-slate-400">▾</span>
      </button>
      {open && (
        <div className="absolute left-0 z-50 mt-1 w-64 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg dark:border-slate-800 dark:bg-[#0d1117]">
          <button
            onClick={() => { setOpen(false); nav("/platform"); }}
            className="mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            🧊 Artik Platform
          </button>
          <div className="my-1 border-t border-slate-100 dark:border-slate-800" />
          {APPS.map((app) => (
            <button
              key={app.id}
              onClick={() => go(app.url, app.current)}
              className="flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <span className="text-xl">{app.icon}</span>
              <span>
                <span className={`block text-sm font-semibold ${app.accent}`}>
                  {app.name}{app.current && <span className="ml-1 text-xs text-slate-400">· current</span>}
                </span>
                <span className="block text-xs text-slate-500 dark:text-slate-400">{app.tagline}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

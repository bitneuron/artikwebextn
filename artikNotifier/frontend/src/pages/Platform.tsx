import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { APPS, APP_ENV, APP_VERSION, CURRENT_APP, PLATFORM_NAME } from "../platform/apps";

// "Artik Platform / Choose your application" — the cross-product landing page.
// Cards are rendered from the app registry, so a newly registered app appears here
// automatically. Public (no auth required).
export default function Platform() {
  const nav = useNavigate();

  useEffect(() => {
    document.title = `${PLATFORM_NAME} — Choose your application`;
  }, []);

  const open = (app: (typeof APPS)[number]) => {
    if (app.current || app.url === "/") nav("/"); // same app → in-app route
    else window.location.href = app.url;           // sibling product → its deployment
  };

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-12 dark:bg-[#0b0f15]">
      <div className="mx-auto max-w-4xl">
        <header className="mb-10 text-center">
          <div className="mb-2 text-4xl">🧊</div>
          <h1 className="text-3xl font-bold tracking-tight">
            Artik <span className="text-brand">Platform</span>
          </h1>
          <p className="mt-2 text-slate-500 dark:text-slate-400">Choose your application</p>
        </header>

        <div className="grid gap-5 sm:grid-cols-2">
          {APPS.map((app) => (
            <button
              key={app.id}
              onClick={() => open(app)}
              className="group flex flex-col items-start rounded-2xl border border-slate-200 bg-white p-6 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-slate-800 dark:bg-[#0d1117]"
            >
              <div className="mb-3 flex w-full items-center justify-between">
                <span className="text-4xl">{app.icon}</span>
                {app.current && (
                  <span className="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand">
                    You are here
                  </span>
                )}
              </div>
              <h2 className={`text-xl font-bold ${app.accent}`}>{app.name}</h2>
              <p className="mt-0.5 text-sm font-medium text-slate-600 dark:text-slate-300">{app.tagline}</p>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{app.description}</p>
              <span className="mt-4 text-sm font-medium text-brand opacity-0 transition group-hover:opacity-100">
                Open {app.short} →
              </span>
            </button>
          ))}
        </div>

        <footer className="mt-10 text-center text-xs text-slate-400">
          {CURRENT_APP.name} · v{APP_VERSION} · {APP_ENV}
        </footer>
      </div>
    </div>
  );
}

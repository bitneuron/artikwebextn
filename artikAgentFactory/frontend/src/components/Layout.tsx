import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

const NAV = [
  { to: "/", label: "Agents", icon: "◇", end: true },
  { to: "/runs", label: "Run History", icon: "▤" },
  { to: "/templates", label: "Templates", icon: "✦" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

const ADMIN_NAV = [
  { to: "/users", label: "Users", icon: "☺" },
  { to: "/audit", label: "Audit Log", icon: "▥" },
];

const TITLES: Record<string, string> = {
  "/": "Agents", "/runs": "Run History", "/templates": "Templates",
  "/settings": "Settings", "/agents/new": "Create Agent", "/users": "Users", "/audit": "Audit Log",
};

const CAN_CREATE_AGENTS = new Set(["administrator", "agent_manager"]);

export default function Layout() {
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const { user, logout } = useAuth();

  useEffect(() => {
    const title = TITLES[loc.pathname] ?? "artikAgentFactory";
    document.title = `artikAgentFactory — ${title}`;
  }, [loc.pathname]);

  return (
    <div className="grain relative min-h-screen bg-void md:grid md:grid-cols-[240px_1fr]">
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border bg-surface/80 backdrop-blur-xl transition-transform md:relative md:w-auto md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <button
          onClick={() => { setOpen(false); nav("/"); }}
          className="flex items-center gap-2.5 px-5 pb-1 pt-6 text-left"
        >
          <svg width="26" height="26" viewBox="0 0 100 100" className="shrink-0">
            <defs>
              <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#4d7fff" />
                <stop offset="1" stopColor="#9b6bff" />
              </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="14" fill="url(#logo-g)" />
            <circle cx="50" cy="14" r="6" fill="url(#logo-g)" opacity="0.85" />
            <circle cx="50" cy="86" r="6" fill="url(#logo-g)" opacity="0.85" />
            <circle cx="14" cy="50" r="6" fill="url(#logo-g)" opacity="0.85" />
            <circle cx="86" cy="50" r="6" fill="url(#logo-g)" opacity="0.85" />
          </svg>
          <span className="font-display text-[15px] font-bold leading-none">
            artik<span className="bg-grad-brand bg-clip-text text-transparent">Agent</span>Factory
          </span>
        </button>
        <div className="px-5 pb-5 pt-1 text-[11px] font-medium tracking-wide text-ink-mute">
          Research that keeps working.
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                  isActive
                    ? "bg-gradient-to-r from-blue/15 to-violet/10 text-ink shadow-[inset_0_0_0_1px_rgba(77,127,255,0.25)]"
                    : "text-ink-dim hover:bg-surface-2 hover:text-ink"
                }`
              }
            >
              <span className="w-4 text-center text-base opacity-80">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
          {user?.role === "administrator" && (
            <>
              <div className="my-2 border-t border-border" />
              {ADMIN_NAV.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                      isActive
                        ? "bg-gradient-to-r from-blue/15 to-violet/10 text-ink shadow-[inset_0_0_0_1px_rgba(77,127,255,0.25)]"
                        : "text-ink-dim hover:bg-surface-2 hover:text-ink"
                    }`
                  }
                >
                  <span className="w-4 text-center text-base opacity-80">{n.icon}</span>
                  {n.label}
                </NavLink>
              ))}
            </>
          )}
        </nav>

        {user && CAN_CREATE_AGENTS.has(user.role) && (
          <div className="mx-3 mb-3 rounded-xl border border-border bg-surface-2 p-3">
            <button className="btn-primary btn-sm w-full" onClick={() => { setOpen(false); nav("/agents/new"); }}>
              + Create Agent
            </button>
          </div>
        )}

        <div className="flex items-center gap-2 border-t border-border px-5 py-4">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-3 text-xs font-bold text-ink-dim">
            {(user?.full_name || user?.username || "?")[0].toUpperCase()}
          </div>
          <div className="min-w-0 flex-1 text-xs">
            <div className="truncate font-semibold text-ink">{user?.full_name || user?.username}</div>
            <div className="truncate text-ink-mute">{user?.role.replace("_", " ")}</div>
          </div>
          <button
            className="rounded-lg px-2 py-1 text-[11px] font-semibold text-ink-mute hover:bg-surface-2 hover:text-ink"
            onClick={async () => { await logout(); nav("/login"); }}
            title="Sign out"
          >
            Sign out
          </button>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setOpen(false)} />}

      <div className="relative z-10 flex min-h-screen flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-border bg-void/70 px-4 py-3 backdrop-blur md:hidden">
          <button className="text-ink" onClick={() => setOpen(true)} aria-label="Open navigation">☰</button>
          <span className="font-display text-sm font-bold">artikAgentFactory</span>
        </header>
        <main className="flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

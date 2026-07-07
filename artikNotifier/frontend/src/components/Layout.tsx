import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";
import NotificationBell from "./NotificationBell";
import AppSwitcher from "./AppSwitcher";
import { APP_ENV, APP_VERSION } from "../platform/apps";

const NAV = [
  { to: "/", label: "Home", icon: "🏠", end: true },
  { to: "/notes", label: "Notes", icon: "📝" },
  { to: "/notebooks", label: "Notebooks", icon: "📚" },
  { to: "/reminders", label: "Reminders", icon: "⏰" },
  { to: "/calendar", label: "Calendar", icon: "🗓️" },
  { to: "/notifications", label: "Notifications", icon: "🔔" },
  { to: "/assistant", label: "AI Copilot", icon: "🤖" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
];

// Per-route browser-tab titles → "ArtikNotifier — <Page>"
const TITLES: Record<string, string> = {
  "/": "Home", "/notes": "Notes", "/notebooks": "Notebooks",
  "/reminders": "Reminders", "/calendar": "Calendar",
  "/notifications": "Notifications", "/assistant": "AI Copilot",
  "/settings": "Settings", "/admin": "Admin",
};

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const base = loc.pathname.startsWith("/reminders/") ? "Reminder"
      : TITLES[loc.pathname] ?? "Dashboard";
    document.title = `ArtikNotifier — ${base}`;
  }, [loc.pathname]);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      {/* sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-56 border-r border-slate-200 bg-white p-4 transition-transform dark:border-slate-800 dark:bg-[#0b0f15] md:relative md:w-auto md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <button
          onClick={() => { setOpen(false); nav("/platform"); }}
          className="mb-6 flex items-center gap-2 text-lg font-bold"
          title="Artik Platform"
        >
          🔔 Artik <span className="text-brand">Notifier</span>
        </button>
        <nav className="space-y-1">
          {[...NAV, ...(user?.role === "admin" ? [{ to: "/admin", label: "Admin", icon: "🛡️" }] : [])].map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${
                  isActive ? "bg-brand/10 text-brand" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`
              }
            >
              <span>{n.icon}</span> {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="absolute bottom-4 left-4 text-[11px] text-slate-400">
          v{APP_VERSION} · {APP_ENV}
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setOpen(false)} />}

      {/* main */}
      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur dark:border-slate-800 dark:bg-[#0d1117]/80">
          <button className="md:hidden" onClick={() => setOpen(true)}>☰</button>
          <AppSwitcher />
          <button className="btn-primary !px-3 !py-1.5" onClick={() => nav("/notes")}>+ New Note</button>
          <div className="ml-auto flex items-center gap-3">
            <NotificationBell />
            <button className="text-lg" title="Toggle theme" onClick={toggle}>{theme === "dark" ? "🌙" : "☀️"}</button>
            <div className="hidden text-right text-xs sm:block">
              <div className="font-semibold">{user?.full_name || user?.email}</div>
              <div className="text-slate-400">{user?.role}</div>
            </div>
            <button className="btn-ghost !px-3 !py-1.5" onClick={() => { logout(); nav("/login"); }}>Sign out</button>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6"><Outlet /></main>
      </div>
    </div>
  );
}

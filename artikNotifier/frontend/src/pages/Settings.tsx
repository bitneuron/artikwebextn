import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Options } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";

interface Prefs {
  theme: string; default_channels: string;
  email_notifications: boolean; in_app_notifications: boolean; digest_enabled: boolean;
}

export default function Settings() {
  const { user } = useAuth();
  const { theme, toggle } = useTheme();
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [msg, setMsg] = useState("");

  useEffect(() => { api.get<Prefs>("/api/preferences").then(setPrefs); }, []);
  useEffect(() => { api.get<Options>("/api/options").then(setOptions); }, []);

  async function savePrefs(patch: Partial<Prefs>) {
    const updated = await api.put<Prefs>("/api/preferences", patch);
    setPrefs(updated);
  }

  function toggleDefaultChannel(ch: string) {
    if (!prefs) return;
    const set = new Set(prefs.default_channels.split(",").map((s) => s.trim()).filter(Boolean));
    set.has(ch) ? set.delete(ch) : set.add(ch);
    savePrefs({ default_channels: Array.from(set).join(",") });
  }
  async function changePassword(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    try {
      await api.post("/api/auth/change-password", pw);
      setMsg("Password updated."); setPw({ current_password: "", new_password: "" });
    } catch (e: any) { setMsg(e.message || "Failed"); }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-xl font-bold">Settings</h1>

      <div className="card space-y-2">
        <h2 className="font-semibold">Account</h2>
        <div className="text-sm text-slate-400">{user?.full_name} · {user?.email} · <span className="badge bg-slate-500/15">{user?.role}</span></div>
      </div>

      <div className="card space-y-3">
        <h2 className="font-semibold">Appearance</h2>
        <label className="flex items-center justify-between text-sm">
          Theme <button className="btn-ghost !py-1.5" onClick={toggle}>{theme === "dark" ? "🌙 Dark" : "☀️ Light"}</button>
        </label>
      </div>

      {prefs && (
        <div className="card space-y-3">
          <h2 className="font-semibold">Notification preferences</h2>
          <Toggle label="Email notifications" checked={prefs.email_notifications} onChange={(v) => savePrefs({ email_notifications: v })} />
          <Toggle label="In-app notifications" checked={prefs.in_app_notifications} onChange={(v) => savePrefs({ in_app_notifications: v })} />
          <Toggle label="Daily digest" checked={prefs.digest_enabled} onChange={(v) => savePrefs({ digest_enabled: v })} />

          <div className="pt-1">
            <div className="mb-1.5 text-sm">Default channels for new reminders</div>
            <div className="flex flex-wrap gap-2">
              {(options?.channels ?? ["email", "in_app", "slack"]).map((c) => {
                const on = prefs.default_channels.split(",").map((s) => s.trim()).includes(c);
                return (
                  <button type="button" key={c} onClick={() => toggleDefaultChannel(c)}
                    className={`badge cursor-pointer border ${on ? "border-brand bg-brand/15 text-brand" : "border-slate-300 text-slate-500 dark:border-slate-700"}`}>
                    {c}
                  </button>
                );
              })}
            </div>
            <p className="mt-1 text-xs text-slate-400">New reminders pre-select these channels (you can still change them per reminder).</p>
          </div>
        </div>
      )}

      <form onSubmit={changePassword} className="card space-y-3">
        <h2 className="font-semibold">Change password</h2>
        <input className="input" type="password" placeholder="Current password" value={pw.current_password}
          onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required />
        <input className="input" type="password" placeholder="New password" value={pw.new_password}
          onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required />
        {msg && <p className="text-sm text-brand">{msg}</p>}
        <button className="btn-primary">Update password</button>
      </form>
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between text-sm">
      {label}
      <input type="checkbox" className="h-4 w-4 accent-brand" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

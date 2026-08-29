import { FormEvent, useEffect, useState } from "react";
import { CurrentUser, Role, usersApi } from "../api/auth";
import { useAuth } from "../contexts/AuthContext";
import { relativeTime } from "../lib/format";

const ROLES: Role[] = ["administrator", "agent_manager", "researcher", "viewer"];

export default function UsersAdmin() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<CurrentUser[] | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ email: "", username: "", full_name: "", password: "", role: "viewer" as Role });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setUsers(await usersApi.list());
  }
  useEffect(() => {
    load();
  }, []);

  async function createUser(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await usersApi.create(form);
      setForm({ email: "", username: "", full_name: "", password: "", role: "viewer" });
      setShowCreate(false);
      load();
    } catch (err: any) {
      setError(err.message ?? "Failed to create user");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight text-ink">Users</h1>
          <p className="mt-1.5 text-sm text-ink-dim">Manage who can access this workspace and what they can do.</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate((s) => !s)}>+ Add User</button>
      </div>

      {showCreate && (
        <form onSubmit={createUser} className="card mt-6 space-y-4 p-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="new-email">Email</label>
              <input id="new-email" type="email" className="input" required value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="new-username">Username</label>
              <input id="new-username" className="input" required value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="new-fullname">Full name</label>
              <input id="new-fullname" className="input" value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="new-role">Role</label>
              <select id="new-role" className="select" value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="label" htmlFor="new-password">Temporary password</label>
              <input id="new-password" type="password" className="input" required value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <p className="mt-1 text-[11px] text-ink-mute">At least 12 characters. The user must change it on first login.</p>
            </div>
          </div>
          {error && <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div>}
          <div className="flex gap-2">
            <button type="submit" className="btn-primary" disabled={busy}>{busy ? "Creating…" : "Create user"}</button>
            <button type="button" className="btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </form>
      )}

      <div className="card mt-6 overflow-x-auto">
        <table className="w-full min-w-[600px] text-sm">
          <thead className="bg-surface-2 text-xs uppercase tracking-wide text-ink-mute">
            <tr>
              <th className="px-4 py-2.5 text-left">User</th>
              <th className="px-4 py-2.5 text-left">Role</th>
              <th className="px-4 py-2.5 text-left">Status</th>
              <th className="px-4 py-2.5 text-left">Last login</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {(users ?? []).map((u) => (
              <tr key={u.id} className="border-t border-border/60">
                <td className="px-4 py-2.5">
                  <div className="text-ink">{u.full_name || u.username}</div>
                  <div className="text-xs text-ink-mute">{u.email}</div>
                </td>
                <td className="px-4 py-2.5">
                  <select
                    className="select w-auto !py-1 text-xs" value={u.role} disabled={u.id === me?.id}
                    onChange={async (e) => { await usersApi.update(u.id, { role: e.target.value as Role }); load(); }}
                  >
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="px-4 py-2.5">
                  {u.is_active ? <span className="badge-ok">active</span> : <span className="badge-mute">disabled</span>}
                  {u.must_reset_password && <span className="badge-warn ml-1">reset pending</span>}
                </td>
                <td className="px-4 py-2.5 text-xs text-ink-dim">{u.last_login_at ? relativeTime(u.last_login_at) : "never"}</td>
                <td className="px-4 py-2.5 text-right">
                  <button className="btn-ghost btn-sm" onClick={async () => { await usersApi.forceReset(u.id); load(); }}>
                    Force reset
                  </button>
                  {u.id !== me?.id && (
                    <button
                      className="btn-ghost btn-sm ml-1"
                      onClick={async () => { await usersApi.update(u.id, { is_active: !u.is_active }); load(); }}
                    >
                      {u.is_active ? "Disable" : "Enable"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

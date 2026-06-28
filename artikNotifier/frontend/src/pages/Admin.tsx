import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { User } from "../api/types";
import { fmtDateTime } from "../lib/format";

export default function Admin() {
  const { user } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [err, setErr] = useState("");

  async function load() {
    try { setUsers(await api.get<User[]>("/api/admin/users")); }
    catch (e: any) { setErr(e.message || "Forbidden"); }
  }
  useEffect(() => { load(); }, []);

  if (user?.role !== "admin")
    return <div className="card text-sm text-red-500">Admin access required.</div>;

  async function setRole(id: number, role: string) {
    try { await api.post(`/api/admin/users/${id}/role?role=${role}`); load(); }
    catch (e: any) { alert(e.message); }
  }
  async function deactivate(id: number) {
    if (!confirm("Deactivate this user?")) return;
    try { await api.post(`/api/admin/users/${id}/deactivate`); load(); }
    catch (e: any) { alert(e.message); }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">🛡️ Admin · User Management</h1>
      {err && <div className="card text-sm text-red-500">{err}</div>}
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs uppercase text-slate-400">
            <th className="p-2">Email</th><th className="p-2">Name</th><th className="p-2">Role</th>
            <th className="p-2">Status</th><th className="p-2">Last login</th><th className="p-2">Actions</th>
          </tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="p-2">{u.email}</td>
                <td className="p-2 text-slate-400">{u.full_name || "—"}</td>
                <td className="p-2"><span className="badge bg-slate-500/15">{u.role}</span></td>
                <td className="p-2">{u.is_active
                  ? <span className="badge bg-emerald-500/15 text-emerald-500">active</span>
                  : <span className="badge bg-red-500/15 text-red-500">inactive</span>}</td>
                <td className="p-2 text-slate-400">{fmtDateTime(u.last_login_at)}</td>
                <td className="p-2 whitespace-nowrap">
                  <button className="btn-ghost !px-2 !py-1 !text-xs" onClick={() => setRole(u.id, u.role === "admin" ? "user" : "admin")}>
                    {u.role === "admin" ? "↓ user" : "↑ admin"}
                  </button>
                  {u.id !== user.id && (
                    <button className="btn-ghost !px-2 !py-1 !text-xs" onClick={() => deactivate(u.id)}>⏸</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-400">Admins manage accounts only — reminder/notification content stays private to each user.</p>
    </div>
  );
}

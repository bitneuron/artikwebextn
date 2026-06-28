import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.password.length < 8) { setErr("Password must be at least 8 characters"); return; }
    setBusy(true); setErr("");
    try { await register(form.email, form.password, form.full_name); nav("/"); }
    catch (e: any) { setErr(e.message || "Registration failed"); }
    finally { setBusy(false); }
  }

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm">
        <h1 className="mb-1 text-xl font-bold">🔔 Artik Notifier</h1>
        <p className="mb-5 text-sm text-slate-400">Create your account</p>
        <label className="label">Full name</label>
        <input className="input mb-3" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} autoFocus />
        <label className="label">Email</label>
        <input className="input mb-3" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        <label className="label">Password</label>
        <input className="input mb-3" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        {err && <p className="mb-3 text-sm text-red-500">{err}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        <p className="mt-4 text-center text-sm text-slate-400">
          Have an account? <Link to="/login" className="text-brand">Sign in</Link>
        </p>
      </form>
    </div>
  );
}

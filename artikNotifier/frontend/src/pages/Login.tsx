import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await login(email, password); nav("/"); }
    catch (e: any) { setErr(e.message || "Login failed"); }
    finally { setBusy(false); }
  }

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm">
        <h1 className="mb-1 text-xl font-bold">🔔 Artik Notifier</h1>
        <p className="mb-5 text-sm text-slate-400">Sign in to your account</p>
        <label className="label">Email</label>
        <input className="input mb-3" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        <label className="label">Password</label>
        <input className="input mb-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <Link to="/forgot-password" className="mb-3 inline-block text-xs text-brand">Forgot password?</Link>
        {err && <p className="mb-3 text-sm text-red-500">{err}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="mt-4 text-center text-sm text-slate-400">
          No account? <Link to="/register" className="text-brand">Create one</Link>
        </p>
      </form>
    </div>
  );
}

import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [devToken, setDevToken] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const r = await api.post<{ detail: string; dev_token?: string }>("/api/auth/forgot-password", { email });
    setMsg(r.detail);
    setDevToken(r.dev_token ?? null);
  }

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm">
        <h1 className="mb-1 text-xl font-bold">Reset password</h1>
        <p className="mb-5 text-sm text-slate-400">We'll email you a reset link.</p>
        <label className="label">Email</label>
        <input className="input mb-3" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        <button className="btn-primary w-full">Send reset link</button>
        {msg && <p className="mt-3 text-sm text-emerald-500">{msg}</p>}
        {devToken && (
          <p className="mt-2 break-all text-xs text-slate-400">
            Dev link: <Link className="text-brand" to={`/reset-password?token=${devToken}`}>open reset →</Link>
          </p>
        )}
        <p className="mt-4 text-center text-sm"><Link to="/login" className="text-brand">Back to sign in</Link></p>
      </form>
    </div>
  );
}

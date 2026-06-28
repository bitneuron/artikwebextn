import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [token, setToken] = useState(params.get("token") || "");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await api.post("/api/auth/reset-password", { token, new_password: password });
      setDone(true);
      setTimeout(() => nav("/login"), 1500);
    } catch (e: any) { setErr(e.message || "Reset failed"); }
  }

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm">
        <h1 className="mb-1 text-xl font-bold">Set a new password</h1>
        {done ? (
          <p className="mt-3 text-sm text-emerald-500">Password reset! Redirecting to sign in…</p>
        ) : (
          <>
            <label className="label mt-4">Reset token</label>
            <input className="input mb-3" value={token} onChange={(e) => setToken(e.target.value)} required />
            <label className="label">New password</label>
            <input className="input mb-3" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            {err && <p className="mb-3 text-sm text-red-500">{err}</p>}
            <button className="btn-primary w-full">Reset password</button>
          </>
        )}
        <p className="mt-4 text-center text-sm"><Link to="/login" className="text-brand">Back to sign in</Link></p>
      </form>
    </div>
  );
}

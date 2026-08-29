import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { authApi } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../contexts/AuthContext";

function Logo() {
  return (
    <svg width="40" height="40" viewBox="0 0 100 100" className="shrink-0">
      <defs>
        <linearGradient id="login-logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4d7fff" />
          <stop offset="1" stopColor="#9b6bff" />
        </linearGradient>
      </defs>
      <circle cx="50" cy="50" r="14" fill="url(#login-logo-g)" />
      <circle cx="50" cy="14" r="6" fill="url(#login-logo-g)" opacity="0.85" />
      <circle cx="50" cy="86" r="6" fill="url(#login-logo-g)" opacity="0.85" />
      <circle cx="14" cy="50" r="6" fill="url(#login-logo-g)" opacity="0.85" />
      <circle cx="86" cy="50" r="6" fill="url(#login-logo-g)" opacity="0.85" />
    </svg>
  );
}

export default function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const location = useLocation();

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Password-reset stage, entered right after a login that requires it.
  const [needsReset, setNeedsReset] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [resetError, setResetError] = useState<string | null>(null);

  if (user && !needsReset) {
    const from = (location.state as { from?: Location })?.from;
    return <Navigate to={from?.pathname ?? "/"} replace />;
  }

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    if (submitting) return; // guard against double-submit
    setSubmitting(true);
    setError(null);
    try {
      const u = await login(identifier.trim(), password);
      if (u.must_reset_password) setNeedsReset(true);
    } catch (err) {
      // Generic message — never reveal whether the account exists or which field was wrong.
      setError(err instanceof ApiError && err.status === 429 ? err.message : "Invalid email/username or password.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReset(e: FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setResetError(null);
    if (newPassword !== confirmPassword) {
      setResetError("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    try {
      await authApi.changePassword(password, newPassword);
      setNeedsReset(false);
      nav("/", { replace: true });
    } catch (err) {
      setResetError(err instanceof ApiError ? err.message : "Could not update password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grain relative flex min-h-screen items-center justify-center bg-void p-4">
      <div className="pointer-events-none absolute inset-0 bg-grad-radial-hero" />
      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo />
          <h1 className="mt-4 font-display text-xl font-bold text-ink">
            artik<span className="bg-grad-brand bg-clip-text text-transparent">Agent</span>Factory
          </h1>
          <p className="mt-1.5 text-sm text-ink-mute">Research that keeps working.</p>
        </div>

        <div className="card animate-rise-in p-6">
          {!needsReset ? (
            <form onSubmit={handleLogin} className="space-y-4" aria-label="Sign in">
              <div>
                <label className="label" htmlFor="identifier">Email or username</label>
                <input
                  id="identifier" className="input" autoComplete="username" required
                  value={identifier} disabled={submitting}
                  onChange={(e) => setIdentifier(e.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="password">Password</label>
                <input
                  id="password" type="password" className="input" autoComplete="current-password" required
                  value={password} disabled={submitting}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              {error && (
                <div role="alert" className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">
                  {error}
                </div>
              )}
              <button type="submit" className="btn-primary w-full" disabled={submitting}>
                {submitting ? "Signing in…" : "Sign in"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleReset} className="space-y-4" aria-label="Set a new password">
              <p className="text-sm text-ink-dim">Your password needs to be changed before you continue.</p>
              <div>
                <label className="label" htmlFor="new-password">New password</label>
                <input
                  id="new-password" type="password" className="input" autoComplete="new-password" required
                  value={newPassword} disabled={submitting}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="confirm-password">Confirm new password</label>
                <input
                  id="confirm-password" type="password" className="input" autoComplete="new-password" required
                  value={confirmPassword} disabled={submitting}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              {resetError && (
                <div role="alert" className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">
                  {resetError}
                </div>
              )}
              <button type="submit" className="btn-primary w-full" disabled={submitting}>
                {submitting ? "Updating…" : "Update password"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

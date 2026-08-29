import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { authApi, CurrentUser } from "../api/auth";
import { ApiError, setUnauthorizedHandler } from "../api/client";

type AuthState = {
  user: CurrentUser | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const u = await authApi.me();
      setUser(u);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    refresh();
  }, []);

  async function login(identifier: string, password: string) {
    const u = await authApi.login(identifier, password);
    setUser(u);
    return u;
  }

  async function logout() {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
    }
  }

  return (
    <Ctx.Provider value={{ user, loading, login, logout, refresh }}>{children}</Ctx.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

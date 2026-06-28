import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, tokenStore } from "../api/client";
import type { Tokens, User } from "../api/types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, full_name: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>(null as any);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokenStore.access) { setLoading(false); return; }
    api.get<User>("/api/auth/me")
      .then(setUser)
      .catch(() => { tokenStore.access = null; tokenStore.refresh = null; })
      .finally(() => setLoading(false));
  }, []);

  function setTokens(t: Tokens) {
    tokenStore.access = t.access_token;
    tokenStore.refresh = t.refresh_token;
    setUser(t.user);
  }

  async function login(email: string, password: string) {
    setTokens(await api.post<Tokens>("/api/auth/login", { email, password }));
  }
  async function register(email: string, password: string, full_name: string) {
    setTokens(await api.post<Tokens>("/api/auth/register", { email, password, full_name }));
  }
  function logout() {
    api.post("/api/auth/logout", { refresh_token: tokenStore.refresh }).catch(() => {});
    tokenStore.access = null; tokenStore.refresh = null; setUser(null);
  }

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);

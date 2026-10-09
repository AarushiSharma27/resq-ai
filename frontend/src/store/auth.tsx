import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, setUnauthorizedHandler, tokenStore } from '../api/client';
import type { LoginResponse, Role, User } from '../api/types';

interface AuthCtx {
  user: User | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => tokenStore.get());
  const [user, setUser] = useState<User | null>(() => tokenStore.getUser());

  const logout = useCallback(() => {
    tokenStore.clear();
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => { setToken(null); setUser(null); });
    return () => setUnauthorizedHandler(null);
  }, []);

  // Refresh the user profile once on load when a token is present.
  useEffect(() => {
    if (!token) return;
    api.me().then((u) => { setUser(u); tokenStore.setUser(u); }).catch(() => { /* 401 handled globally */ });
  }, [token]);

  const signIn = useCallback((res: LoginResponse) => {
    tokenStore.set(res.access_token);
    tokenStore.setUser(res.user);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    signIn(await api.login(username, password));
  }, [signIn]);

  const register = useCallback(async (username: string, password: string, fullName: string) => {
    signIn(await api.register(username, password, fullName));
  }, [signIn]);

  const hasRole = useCallback((...roles: Role[]) => !!user && roles.includes(user.role), [user]);

  const value = useMemo(() => ({ user, token, login, register, logout, hasRole }), [user, token, login, register, logout, hasRole]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAuth must be used inside AuthProvider');
  return c;
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api } from './api';
import { session } from './session';
import type { JurisdictionLevel, Permission, TokenResponse, UserProfile } from './types';

export interface Credentials {
  level: JurisdictionLevel;
  state_code: string | null;
  district_code: string | null;
  password: string;
}

interface AuthValue {
  user: UserProfile | null;
  expiredNotice: boolean;
  login: (credentials: Credentials) => Promise<void>;
  logout: () => void;
  changePassword: (current: string, next: string) => Promise<void>;
  can: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthValue | null>(null);
const REFRESH_BEFORE_MS = 5 * 60_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(session.user());
  const [expiredNotice, setExpiredNotice] = useState(false);

  useEffect(
    () =>
      session.subscribe((state, reason) => {
        setUser(state?.user ?? null);
        if (!state && reason === 'expired') setExpiredNotice(true);
      }),
    [],
  );

  // Refresh the access token shortly before it expires, while the session is
  // within its maximum length.
  useEffect(() => {
    if (!user) return;
    let timer: ReturnType<typeof setTimeout>;
    const plan = () => {
      const state = session.state();
      if (!state) return;
      const due = state.expiresAt - REFRESH_BEFORE_MS - Date.now();
      timer = setTimeout(async () => {
        const latest = session.state();
        if (!latest || Date.now() > latest.sessionExpiresAt - 60_000) return;
        try {
          session.set(await api.post<TokenResponse>('/api/v1/auth/refresh'));
        } catch {
          /* the next request will surface the expiry */
        }
        plan();
      }, Math.max(5_000, due));
    };
    plan();
    return () => clearTimeout(timer);
  }, [user]);

  const login = useCallback(async (credentials: Credentials) => {
    const response = await api.post<TokenResponse>('/api/v1/auth/login', credentials);
    setExpiredNotice(false);
    session.set(response);
  }, []);

  const logout = useCallback(() => session.clear('signed_out'), []);

  const changePassword = useCallback(async (current: string, next: string) => {
    const response = await api.post<TokenResponse>('/api/v1/auth/change-password', {
      current_password: current,
      new_password: next,
    });
    session.set(response);
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      expiredNotice,
      login,
      logout,
      changePassword,
      can: (permission) => !!user?.permissions.includes(permission),
    }),
    [user, expiredNotice, login, logout, changePassword],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth outside AuthProvider');
  return value;
}

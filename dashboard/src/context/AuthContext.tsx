import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { raahatService } from '../services/raahatService';
import type { AuthSession, JurisdictionItem } from '../types/raahat';

interface AuthContextValue {
  session: AuthSession | null;
  jurisdictions: JurisdictionItem[];
  isAuthenticated: boolean;
  login: (params: {
    state_code: string;
    district_code?: string | null;
    password: string;
    officer_name?: string;
  }) => Promise<void>;
  logout: () => void;
  switchJurisdiction: (params: {
    state_code: string;
    district_code?: string | null;
    password: string;
  }) => Promise<void>;
}

const STORAGE_KEY = 'raahat_auth_session_v3';

// Session shape version: bump this when the AuthSession interface gains required fields.
// A restored session lacking required fields is treated as invalid and discarded.
const SESSION_REQUIRED_FIELDS: (keyof AuthSession)[] = [
  'access_token',
  'state_code',
  'state_name',
  'center_lat',
  'center_lng',
];

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as AuthSession;
        // Discard sessions missing required fields (stale format from prior versions).
        const isValid = SESSION_REQUIRED_FIELDS.every(
          (f) => parsed[f] != null && parsed[f] !== ''
        );
        if (!isValid) {
          localStorage.removeItem(STORAGE_KEY);
          return null;
        }
        raahatService.setToken(parsed.access_token);
        if (parsed.dispatcher_id) {
          raahatService.setDispatcherId(parsed.dispatcher_id);
        }
        return parsed;
      }
    } catch (e) {
      console.warn('Failed to restore auth session from localStorage', e);
    }
    return null;
  });

  const [jurisdictions, setJurisdictions] = useState<JurisdictionItem[]>([]);

  // Fetch jurisdictions list on mount
  useEffect(() => {
    raahatService
      .getJurisdictions()
      .then(setJurisdictions)
      .catch((err) => console.error('Failed to load jurisdictions', err));
  }, []);

  const login = useCallback(
    async (params: {
      state_code: string;
      district_code?: string | null;
      password: string;
      officer_name?: string;
    }) => {
      const newSession = await raahatService.login(params);
      setSession(newSession);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(newSession));
      } catch (e) {
        console.warn('Failed to save auth session to localStorage', e);
      }
    },
    []
  );

  const logout = useCallback(() => {
    setSession(null);
    raahatService.setToken(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
      // Also remove any legacy key variants to prevent stale session resurrection.
      localStorage.removeItem('raahat_auth_session_v2');
      localStorage.removeItem('raahat_auth_session');
    } catch {
      // ignore
    }
  }, []);

  const switchJurisdiction = useCallback(
    async (params: {
      state_code: string;
      district_code?: string | null;
      password: string;
    }) => {
      await login({
        state_code: params.state_code,
        district_code: params.district_code,
        password: params.password,
        officer_name: session?.officer_name,
      });
    },
    [login, session]
  );

  return (
    <AuthContext.Provider
      value={{
        session,
        jurisdictions,
        isAuthenticated: session !== null,
        login,
        logout,
        switchJurisdiction,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

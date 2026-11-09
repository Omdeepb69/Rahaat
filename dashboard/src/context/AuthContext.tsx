import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const DEFAULT_DISPATCHER: AuthUser = {
  id: '00000000-0000-0000-0000-000000000001',
  name: 'Dispatcher Alpha',
  email: 'dispatcher.alpha@raahat.gov.in',
  role: 'Lead Emergency Dispatcher',
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: 'jwt-lead-dispatcher-token',
    user: DEFAULT_DISPATCHER,
  });

  const login = useCallback(async (_email: string, _password: string) => {
    setState({
      token: 'jwt-lead-dispatcher-token',
      user: DEFAULT_DISPATCHER,
    });
  }, []);

  const logout = useCallback(() => {
    setState({ token: null, user: null });
  }, []);

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        logout,
        isAuthenticated: state.token !== null,
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

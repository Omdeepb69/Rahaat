/**
 * Access-token storage.
 *
 * The token is kept in memory and mirrored to sessionStorage so a page reload
 * in the same tab keeps the operator signed in; closing the tab ends the
 * session. Nothing is written to localStorage or cookies.
 */
import type { TokenResponse, UserProfile } from './types';

const KEY = 'raahat.session.v1';

interface Stored {
  token: string;
  expiresAt: number;
  sessionExpiresAt: number;
  user: UserProfile;
}

type Listener = (state: Stored | null, reason?: 'expired' | 'signed_out') => void;

let current: Stored | null = load();
const listeners = new Set<Listener>();

function load(): Stored | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Stored;
    if (!parsed.token || parsed.expiresAt <= Date.now()) return null;
    return parsed;
  } catch {
    return null;
  }
}

function persist(): void {
  try {
    if (current) sessionStorage.setItem(KEY, JSON.stringify(current));
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable (private mode): memory only */
  }
}

export const session = {
  token(): string | null {
    return current && current.expiresAt > Date.now() ? current.token : null;
  },
  user(): UserProfile | null {
    return current?.user ?? null;
  },
  state(): Stored | null {
    return current;
  },
  set(response: TokenResponse): void {
    current = {
      token: response.access_token,
      expiresAt: Date.parse(response.expires_at),
      sessionExpiresAt: Date.parse(response.session_expires_at),
      user: response.user,
    };
    persist();
    listeners.forEach((l) => l(current));
  },
  clear(reason: 'expired' | 'signed_out' = 'signed_out'): void {
    if (!current) return;
    current = null;
    persist();
    listeners.forEach((l) => l(null, reason));
  },
  expire(): void {
    session.clear('expired');
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

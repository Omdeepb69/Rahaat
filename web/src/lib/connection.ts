/**
 * Backend reachability, from two sources: the outcome of every API call, and
 * a readiness probe every 15 seconds (more often while offline). The
 * interface uses this to say plainly when the server cannot be reached and
 * how old the data on screen is.
 */
import { apiHeaders, config } from './config';

export type BackendState = 'unknown' | 'online' | 'degraded' | 'offline';

export interface ConnectionSnapshot {
  backend: BackendState;
  lastContactAt: number | null;
  offlineSince: number | null;
  detail: string | null;
}

type Listener = (snapshot: ConnectionSnapshot) => void;

let snapshot: ConnectionSnapshot = { backend: 'unknown', lastContactAt: null, offlineSince: null, detail: null };
const listeners = new Set<Listener>();
let failures = 0;
let timer: ReturnType<typeof setTimeout> | null = null;

function emit(next: Partial<ConnectionSnapshot>): void {
  const merged = { ...snapshot, ...next };
  if (
    merged.backend === snapshot.backend &&
    merged.lastContactAt === snapshot.lastContactAt &&
    merged.detail === snapshot.detail
  ) {
    return;
  }
  snapshot = merged;
  listeners.forEach((l) => l(snapshot));
}

async function probe(): Promise<void> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8_000);
  try {
    const response = await fetch(`${config.apiBaseUrl}/health/ready`, { headers: apiHeaders, signal: controller.signal, cache: 'no-store' });
    if (response.ok) {
      connection.reportSuccess();
      return;
    } else {
      failures = 0;
      emit({ backend: 'degraded', lastContactAt: Date.now(), detail: 'The server is running but its database is not responding.' });
    }
  } catch {
    // A failed health probe is conclusive: the endpoint does no work.
    failures = Math.max(failures, 1);
    connection.reportFailure();
  } finally {
    clearTimeout(timeout);
  }
}

function schedule(): void {
  if (timer) clearTimeout(timer);
  const delay = snapshot.backend === 'online' ? 15_000 : 5_000;
  timer = setTimeout(async () => {
    await probe();
    schedule();
  }, delay);
}

export const connection = {
  snapshot: (): ConnectionSnapshot => snapshot,
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  reportSuccess(): void {
    failures = 0;
    emit({ backend: 'online', lastContactAt: Date.now(), offlineSince: null, detail: null });
  },
  reportFailure(): void {
    failures += 1;
    // One failed data request can be a blip; two in a row, or a failed
    // health probe, is an outage.
    if (failures >= 2 || snapshot.backend === 'unknown') {
      emit({
        backend: 'offline',
        offlineSince: snapshot.offlineSince ?? Date.now(),
        detail: navigator.onLine === false ? 'This device is offline.' : 'The RAAHAT server cannot be reached.',
      });
    }
  },
  start(): () => void {
    void probe().then(schedule);
    const now = () => void probe();
    window.addEventListener('online', now);
    window.addEventListener('focus', now);
    window.addEventListener('offline', () => connection.reportFailure());
    return () => {
      if (timer) clearTimeout(timer);
      window.removeEventListener('online', now);
      window.removeEventListener('focus', now);
    };
  },
  /** Probe now, e.g. when the event stream drops, instead of waiting for the next interval. */
  checkNow: () => void probe().then(schedule),
};

/** Wires the change stream and the connection monitor into React. */
import { useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';

import { connection, type ConnectionSnapshot } from './connection';
import { ChangeStream, type StreamSnapshot } from './realtime';
import type { StreamChange } from './types';

const StreamContext = createContext<StreamSnapshot>({ state: 'idle', lastMessageAt: null, lastSeq: null });
const ChangeListeners = createContext<Set<(c: StreamChange) => void>>(new Set());

/** Query groups each kind of change can affect. */
function groupsFor(change: StreamChange): string[][] {
  const type = change.entity_type;
  if (type === 'incident' || type === 'report') return [['incidents'], ['reports'], ['dispatch']];
  if (type === 'assignment') return [['dispatch'], ['incidents'], ['resources']];
  if (type === 'resource') return [['resources'], ['dispatch']];
  if (type === 'disaster') return [['operations']];
  if (type === 'user') return [['users']];
  return [];
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [snapshot, setSnapshot] = useState<StreamSnapshot>({ state: 'idle', lastMessageAt: null, lastSeq: null });
  const listeners = useRef(new Set<(c: StreamChange) => void>());

  useEffect(() => connection.start(), []);

  useEffect(() => {
    // Changes arrive in bursts (one report produces several). Coalesce
    // invalidations so each query refetches once per burst.
    let pending = new Map<string, string[]>();
    let flush: ReturnType<typeof setTimeout> | null = null;
    const schedule = (groups: string[][]) => {
      groups.forEach((g) => pending.set(g.join('/'), g));
      if (flush) return;
      flush = setTimeout(() => {
        const batch = pending;
        pending = new Map();
        flush = null;
        batch.forEach((queryKey) => void client.invalidateQueries({ queryKey }));
      }, 250);
    };
    const stream = new ChangeStream({
      onChange: (change) => {
        schedule([...groupsFor(change), ['audit']]);
        listeners.current.forEach((l) => l(change));
      },
      onResync: () => void client.invalidateQueries(),
      onDrop: () => connection.checkNow(),
    });
    const unsubscribe = stream.subscribe(setSnapshot);
    stream.start();
    return () => {
      unsubscribe();
      stream.stop();
      if (flush) clearTimeout(flush);
    };
  }, [client]);

  return (
    <StreamContext.Provider value={snapshot}>
      <ChangeListeners.Provider value={listeners.current}>{children}</ChangeListeners.Provider>
    </StreamContext.Provider>
  );
}

export function useStream(): StreamSnapshot {
  return useContext(StreamContext);
}

export function useChanges(listener: (change: StreamChange) => void): void {
  const listeners = useContext(ChangeListeners);
  const ref = useRef(listener);
  ref.current = listener;
  useEffect(() => {
    const wrapped = (c: StreamChange) => ref.current(c);
    listeners.add(wrapped);
    return () => {
      listeners.delete(wrapped);
    };
  }, [listeners]);
}

export function useConnection(): ConnectionSnapshot {
  return useSyncExternalStore(connection.subscribe, connection.snapshot, connection.snapshot);
}

/** Re-render on an interval, for ages and "updated N s ago" labels. */
export function useNow(intervalMs = 10_000): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

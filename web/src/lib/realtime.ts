/**
 * Realtime change stream.
 *
 * Server-Sent Events read through fetch, because the browser EventSource API
 * cannot send an Authorization header. The client remembers the last sequence
 * number it saw and sends it as Last-Event-ID on reconnect, so changes made
 * while it was disconnected are replayed. If the server says the gap is too
 * large (`resync`), every query is refetched instead.
 *
 * Status is reported honestly: "live" only while a stream is open and has
 * produced a message or heartbeat within the last 40 seconds.
 */
import { buildUrl } from './api';
import { session } from './session';
import type { StreamChange } from './types';
import { apiHeaders } from './config';

export type StreamState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'stopped';

export interface StreamSnapshot {
  state: StreamState;
  lastMessageAt: number | null;
  lastSeq: number | null;
}

interface Handlers {
  onChange: (change: StreamChange) => void;
  onResync: () => void;
  onDrop?: () => void;
}

const HEARTBEAT_GRACE_MS = 40_000;

export class ChangeStream {
  private snapshot: StreamSnapshot = { state: 'idle', lastMessageAt: null, lastSeq: null };
  private listeners = new Set<(s: StreamSnapshot) => void>();
  private controller: AbortController | null = null;
  private stopped = false;
  private attempt = 0;
  private watchdog: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly handlers: Handlers) {}

  subscribe(listener: (s: StreamSnapshot) => void): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    return () => this.listeners.delete(listener);
  }

  get current(): StreamSnapshot {
    return this.snapshot;
  }

  private set(next: Partial<StreamSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...next };
    this.listeners.forEach((l) => l(this.snapshot));
  }

  start(): void {
    this.stopped = false;
    this.watchdog = setInterval(() => {
      const last = this.snapshot.lastMessageAt;
      if (this.snapshot.state === 'live' && last && Date.now() - last > HEARTBEAT_GRACE_MS) {
        // Silent connection: the tunnel or laptop went away without closing it.
        this.controller?.abort();
      }
    }, 5_000);
    void this.loop();
  }

  stop(): void {
    this.stopped = true;
    this.controller?.abort();
    if (this.watchdog) clearInterval(this.watchdog);
    this.set({ state: 'stopped' });
  }

  private async loop(): Promise<void> {
    while (!this.stopped) {
      const token = session.token();
      if (!token) {
        this.set({ state: 'stopped' });
        return;
      }
      this.set({ state: this.attempt === 0 ? 'connecting' : 'reconnecting' });
      this.controller = new AbortController();
      try {
        const headers: Record<string, string> = { ...apiHeaders, Authorization: `Bearer ${token}`, Accept: 'text/event-stream' };
        if (this.snapshot.lastSeq !== null) headers['Last-Event-ID'] = String(this.snapshot.lastSeq);
        const response = await fetch(buildUrl('/api/v1/events/stream'), {
          headers,
          signal: this.controller.signal,
          cache: 'no-store',
          credentials: 'omit',
        });
        if (response.status === 401) {
          session.expire();
          return;
        }
        if (!response.ok || !response.body) throw new Error(`stream ${response.status}`);
        await this.read(response.body);
      } catch {
        /* fall through to reconnect */
      }
      if (this.stopped) return;
      this.handlers.onDrop?.();
      this.attempt += 1;
      this.set({ state: 'reconnecting' });
      const delay = Math.min(30_000, 1_000 * 2 ** Math.min(this.attempt, 5)) * (0.75 + Math.random() * 0.5);
      await new Promise((r) => setTimeout(r, delay));
    }
  }

  private async read(body: ReadableStream<Uint8Array>): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        this.dispatch(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');
      }
    }
  }

  private dispatch(block: string): void {
    let event = 'message';
    let data = '';
    let id: string | null = null;
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trim();
      else if (line.startsWith('id:')) id = line.slice(3).trim();
    }
    const now = Date.now();
    if (event === 'ready') {
      const payload = JSON.parse(data) as { seq: number; resync: boolean };
      this.attempt = 0;
      const reconnected = this.snapshot.lastSeq !== null;
      this.set({ state: 'live', lastMessageAt: now, lastSeq: payload.seq });
      // A first connection, or a gap too large to replay: refetch everything.
      if (payload.resync || !reconnected) this.handlers.onResync();
      return;
    }
    if (event === 'heartbeat') {
      this.set({ state: 'live', lastMessageAt: now });
      return;
    }
    if (event === 'change' && data) {
      const change = JSON.parse(data) as StreamChange;
      this.set({ state: 'live', lastMessageAt: now, lastSeq: id ? Number(id) : change.seq });
      this.handlers.onChange(change);
    }
  }
}

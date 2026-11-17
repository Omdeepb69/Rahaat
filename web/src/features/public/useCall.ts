import { useEffect, useMemo, useSyncExternalStore } from 'react';

import { ApiError, buildUrl, errorMessage, request } from '../../lib/api';
import { apiHeaders } from '../../lib/config';
import { VoiceLine } from './voice/line';

export interface PromptLine { language: string; key: string; text: string }

export interface CallFacts {
  people_count: number | null;
  trapped: boolean;
  medical: boolean;
  place: string | null;
  phone: string | null;
  name: string | null;
}

export interface CallState {
  call_id: string;
  step: string;
  language: string;
  language_name: string;
  language_source: 'default' | 'detected' | 'script' | 'chosen';
  district: string;
  state: string;
  prompt: PromptLine[];
  facts: CallFacts;
  done: boolean;
  ticket: string | null;
}

interface StartedCall extends CallState { token: string }
interface TurnResult extends CallState { heard: string; via: 'voice' | 'text'; speech_failed: boolean }

/**
 * connecting: opening the call · speaking: the agent is asking ·
 * listening: waiting for the caller · hearing: the caller is talking ·
 * sending: the answer is being understood · waiting: needs the caller to act
 */
export type Phase = 'idle' | 'connecting' | 'speaking' | 'listening' | 'hearing' | 'sending' | 'waiting' | 'done' | 'failed';

export interface Entry { id: number; who: 'agent' | 'caller'; text: string; language: string; via?: 'voice' | 'text' }

export interface Position { latitude: number; longitude: number; accuracy_m: number | null }

export interface Snapshot {
  phase: Phase;
  call: CallState | null;
  entries: Entry[];
  level: number;
  microphone: boolean | null;
  voiceAvailable: boolean;
  notice: string | null;
  error: string | null;
  canResend: boolean;
  position: Position | null;
}

const INITIAL: Snapshot = {
  phase: 'idle', call: null, entries: [], level: 0, microphone: null, voiceAvailable: true,
  notice: null, error: null, canResend: false, position: null,
};

/** One guided call: asks, listens, sends, repeats until the report is sent. */
export class CallController {
  private snapshot: Snapshot = INITIAL;
  private listeners = new Set<() => void>();
  private line: VoiceLine | null = null;
  private session: { id: string; token: string } | null = null;
  private prompts = new Map<string, Promise<ArrayBuffer | null>>();
  private unsent: { audio: Blob | null; text: string | null } | null = null;
  private answered = false;
  private generation = 0;
  private nextEntry = 1;
  private disposed = false;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  get = () => this.snapshot;

  private set(patch: Partial<Snapshot>) {
    this.snapshot = { ...this.snapshot, ...patch };
    this.listeners.forEach((l) => l());
  }

  private say(entry: Omit<Entry, 'id'>) {
    this.set({ entries: [...this.snapshot.entries, { ...entry, id: this.nextEntry++ }] });
  }

  private get headers() {
    return { 'X-Call-Token': this.session?.token ?? '' };
  }

  private prompt(line: PromptLine): Promise<ArrayBuffer | null> {
    const key = `${line.language}/${line.key}`;
    let pending = this.prompts.get(key);
    if (!pending) {
      pending = fetch(buildUrl(`/api/v1/public/voice/${line.language}/${line.key}.wav`), { mode: 'cors', credentials: 'omit', headers: apiHeaders })
        .then((r) => (r.ok ? r.arrayBuffer() : null))
        .catch(() => null);
      this.prompts.set(key, pending);
      void pending.then((data) => { if (!data) this.prompts.delete(key); });
    }
    return pending;
  }

  private async speak(lines: PromptLine[], turn: number) {
    if (turn !== this.generation) return;
    this.set({ phase: this.snapshot.phase === 'done' ? 'done' : 'speaking' });
    lines.forEach((l) => this.say({ who: 'agent', text: l.text, language: l.language }));
    const audio = await Promise.all(lines.map((l) => this.prompt(l)));
    if (audio.some((a) => a === null)) this.set({ voiceAvailable: false });
    for (const data of audio) {
      if (turn !== this.generation || this.disposed || !data || !this.line) return;
      try {
        await this.line.play(data);
      } catch {
        this.set({ voiceAvailable: false });
      }
    }
  }

  private apply(next: CallState) {
    this.set({ call: next, ...(next.done ? { phase: 'done' as Phase } : {}) });
  }

  private async listen(turn: number) {
    if (turn !== this.generation || this.disposed) return;
    const step = this.snapshot.call?.step;
    if (!step || this.snapshot.call?.done) return;
    if (!this.line?.hasMicrophone) {
      this.set({ phase: 'waiting' });
      return;
    }
    this.set({ phase: 'listening' });
    const heard = await this.line.listen({
      onLevel: (level) => this.set({ level }),
      onSpeech: () => { if (turn === this.generation) this.set({ phase: 'hearing' }); },
    });
    if (turn !== this.generation || this.disposed) return;
    await this.send(step, heard.wav, null, turn);
  }

  private async send(step: string, audio: Blob | null, text: string | null, turn: number) {
    if (!this.session) return;
    this.set({ phase: 'sending', canResend: false });
    this.unsent = null;
    const form = new FormData();
    form.set('step', step);
    if (text) form.set('text', text);
    if (audio) form.set('audio', audio, 'answer.wav');
    let result: TurnResult;
    try {
      result = await request<TurnResult>(`/api/v1/public/calls/${this.session.id}/turns`, {
        method: 'POST', body: form, auth: false, headers: this.headers, timeoutMs: 45_000,
      });
    } catch (e) {
      if (turn !== this.generation) return;
      if (e instanceof ApiError && (e.status === 409 || e.status === 404)) {
        this.set({ phase: 'failed', error: e.message });
        return;
      }
      this.unsent = { audio, text };
      this.set({ phase: 'waiting', canResend: true, notice: 'Your answer did not reach us. Check your connection, then send it again.' });
      return;
    }
    if (turn !== this.generation) return;
    if (result.heard) {
      this.answered = true;
      this.say({ who: 'caller', text: result.heard, language: result.language, via: result.via });
    }
    this.set({
      notice: result.speech_failed ? 'We could not understand that recording. Please say it again, or type your answer.' : null,
    });
    this.apply(result);
    await this.speak(result.prompt, turn);
    if (!result.done) await this.listen(turn);
  }

  async start(stateCode: string, districtCode: string) {
    const turn = ++this.generation;
    this.set({ ...INITIAL, phase: 'connecting', position: this.snapshot.position });
    this.answered = false;
    this.line?.close();
    this.line = new VoiceLine();
    try {
      await this.line.open();
    } catch {
      this.set({ voiceAvailable: false });
    }
    let started: StartedCall;
    try {
      started = await request<StartedCall>('/api/v1/public/calls', {
        method: 'POST', body: { state_code: stateCode, district_code: districtCode }, auth: false,
      });
    } catch (e) {
      this.set({ phase: 'failed', error: errorMessage(e) });
      return;
    }
    this.session = { id: started.call_id, token: started.token };
    this.apply(started);
    const microphone = await this.line.connectMicrophone();
    this.set({ microphone });
    if (this.snapshot.position) void this.sharePosition(this.snapshot.position);
    await this.speak(started.prompt, turn);
    await this.listen(turn);
  }

  /** The caller typed an answer instead of speaking. */
  async type(text: string) {
    const trimmed = text.trim();
    const step = this.snapshot.call?.step;
    if (!trimmed || !step || this.snapshot.call?.done) return;
    const turn = ++this.generation;
    this.line?.stopPlayback();
    this.line?.cancel();
    await this.send(step, null, trimmed, turn);
  }

  doneSpeaking() {
    this.line?.done();
  }

  async resend() {
    const step = this.snapshot.call?.step;
    if (!this.unsent || !step) return;
    const turn = ++this.generation;
    await this.send(step, this.unsent.audio, this.unsent.text, turn);
  }

  async listenAgain() {
    const turn = ++this.generation;
    this.set({ notice: null });
    await this.listen(turn);
  }

  /** Send what has been said so far. */
  async finish() {
    if (!this.session) return;
    const turn = ++this.generation;
    this.line?.stopPlayback();
    this.line?.cancel();
    this.set({ phase: 'sending' });
    try {
      const result = await request<CallState>(`/api/v1/public/calls/${this.session.id}/finish`, {
        method: 'POST', auth: false, headers: this.headers, query: { reason: 'caller_sent' },
      });
      this.apply(result);
      if (result.ticket) {
        this.session = null;
        await this.speak(result.prompt, turn);
      } else {
        this.set({ phase: 'waiting', notice: 'There is nothing to send yet. Tell us what has happened first.' });
      }
    } catch (e) {
      this.set({ phase: 'waiting', notice: `The report was not sent: ${errorMessage(e)}` });
    }
  }

  async sharePosition(value: Position) {
    this.set({ position: value });
    if (!this.session) return;
    try {
      await request(`/api/v1/public/calls/${this.session.id}/position`, {
        method: 'PUT', auth: false, headers: this.headers,
        body: { latitude: value.latitude, longitude: value.longitude, accuracy_m: value.accuracy_m },
      });
    } catch {
      this.set({ notice: 'Your location could not be attached. Describe where you are instead.' });
    }
  }

  async chooseLanguage(language: string) {
    if (!this.session) return;
    try {
      const result = await request<CallState>(`/api/v1/public/calls/${this.session.id}/language`, {
        method: 'POST', auth: false, headers: this.headers, body: { language },
      });
      this.apply(result);
      const phase = this.snapshot.phase;
      if (language !== 'auto' && (phase === 'listening' || phase === 'waiting')) {
        const turn = ++this.generation;
        this.line?.cancel();
        await this.speak(result.prompt, turn);
        await this.listen(turn);
      }
    } catch {
      this.set({ notice: 'The language could not be changed.' });
    }
  }

  /** Warm the cache for the opening prompts before the caller presses start. */
  preload(lines: PromptLine[]) {
    lines.forEach((l) => void this.prompt(l));
  }

  leave = () => {
    if (!this.session || !this.answered) return;
    const url = buildUrl(`/api/v1/public/calls/${this.session.id}/finish`, { token: this.session.token, reason: 'caller_left' });
    navigator.sendBeacon?.(url);
  };

  attach() {
    this.disposed = false;
  }

  dispose() {
    this.disposed = true;
    this.generation += 1;
    this.line?.close();
    this.line = null;
  }
}

export function useCall() {
  const controller = useMemo(() => new CallController(), []);
  const snapshot = useSyncExternalStore(controller.subscribe, controller.get);
  useEffect(() => {
    controller.attach();
    window.addEventListener('pagehide', controller.leave);
    return () => {
      window.removeEventListener('pagehide', controller.leave);
      controller.leave();
      controller.dispose();
    };
  }, [controller]);
  return { controller, ...snapshot };
}

/**
 * The caller's side of a voice call: microphone capture with end-of-speech
 * detection, and playback of the agent's prompts through the same audio
 * context (so mobile browsers that require a gesture only need one).
 */
import workletUrl from './capture.worklet.js?url';
import { concat, downsample, encodeWav } from './wav';

export interface Heard {
  wav: Blob | null;
  spoke: boolean;
}

export interface ListenOptions {
  onLevel?: (level: number) => void;
  onSpeech?: () => void;
  maxMs?: number;
  silenceMs?: number;
  noSpeechMs?: number;
}

const WINDOW_MS = 30;
const PRE_ROLL_MS = 400;

export class VoiceLine {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioNode | null = null;
  private sink: GainNode | null = null;
  private onChunk: ((chunk: Float32Array) => void) | null = null;
  private playing: AudioBufferSourceNode | null = null;
  private finishListening: (() => void) | null = null;
  private cancelListening: (() => void) | null = null;

  get hasMicrophone(): boolean {
    return this.stream !== null;
  }

  /** Create the audio context. Call from a user gesture. */
  async open(): Promise<void> {
    if (this.context) return;
    const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.context = new Context();
    if (this.context.state === 'suspended') await this.context.resume();
  }

  /** Ask for the microphone. Returns false when it is refused or missing. */
  async connectMicrophone(): Promise<boolean> {
    if (!this.context) await this.open();
    const context = this.context!;
    if (!navigator.mediaDevices?.getUserMedia) return false;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch {
      return false;
    }
    const source = context.createMediaStreamSource(this.stream);
    this.sink = context.createGain();
    this.sink.gain.value = 0;
    this.sink.connect(context.destination);
    const deliver = (chunk: Float32Array) => this.onChunk?.(chunk);
    if (context.audioWorklet) {
      await context.audioWorklet.addModule(workletUrl);
      const worklet = new AudioWorkletNode(context, 'raahat-capture');
      worklet.port.onmessage = (event: MessageEvent<Float32Array>) => deliver(event.data);
      this.node = worklet;
    } else {
      const processor = context.createScriptProcessor(2048, 1, 1);
      processor.onaudioprocess = (event) => deliver(new Float32Array(event.inputBuffer.getChannelData(0)));
      this.node = processor;
    }
    source.connect(this.node);
    this.node.connect(this.sink);
    return true;
  }

  /**
   * Record one answer. Ends after a pause following speech, when the caller
   * says nothing for a while, or when {@link done} is called.
   */
  listen(options: ListenOptions = {}): Promise<Heard> {
    const context = this.context;
    if (!context || !this.stream) return Promise.resolve({ wav: null, spoke: false });
    const { maxMs = 45_000, silenceMs = 1_500, noSpeechMs = 10_000 } = options;
    const rate = context.sampleRate;
    const windowSize = Math.round((rate * WINDOW_MS) / 1000);
    const preRollWindows = Math.ceil(PRE_ROLL_MS / WINDOW_MS);

    return new Promise<Heard>((resolve) => {
      const kept: Float32Array[] = [];
      const preRoll: Float32Array[] = [];
      let pending = new Float32Array(0);
      let floor = 0;
      let calibrated = 0;
      let loud = 0;
      let quietMs = 0;
      let spoke = false;
      const started = performance.now();

      const finish = (cancelled = false) => {
        this.onChunk = null;
        this.finishListening = null;
        this.cancelListening = null;
        options.onLevel?.(0);
        if (cancelled || !spoke) {
          resolve({ wav: null, spoke: false });
          return;
        }
        resolve({ wav: encodeWav(downsample(concat(kept), rate)), spoke: true });
      };
      this.finishListening = () => finish();
      this.cancelListening = () => finish(true);

      this.onChunk = (chunk) => {
        const merged = new Float32Array(pending.length + chunk.length);
        merged.set(pending);
        merged.set(chunk, pending.length);
        let offset = 0;
        while (merged.length - offset >= windowSize) {
          const frame = merged.subarray(offset, offset + windowSize);
          offset += windowSize;
          let sum = 0;
          for (const v of frame) sum += v * v;
          const rms = Math.sqrt(sum / frame.length);
          options.onLevel?.(Math.min(1, rms * 12));

          if (calibrated < 10) {
            floor = (floor * calibrated + rms) / (calibrated + 1);
            calibrated += 1;
          }
          const threshold = Math.max(0.012, floor * 2.5);
          const copy = frame.slice();
          if (!spoke) {
            preRoll.push(copy);
            if (preRoll.length > preRollWindows) preRoll.shift();
            loud = rms > threshold ? loud + 1 : 0;
            if (loud >= 4) {
              spoke = true;
              kept.push(...preRoll);
              options.onSpeech?.();
            } else if (calibrated >= 10) {
              floor = floor * 0.98 + rms * 0.02;
            }
          } else {
            kept.push(copy);
            quietMs = rms < threshold * 0.8 ? quietMs + WINDOW_MS : 0;
          }
          const elapsed = performance.now() - started;
          if ((spoke && quietMs >= silenceMs) || elapsed >= maxMs || (!spoke && elapsed >= noSpeechMs)) {
            finish();
            return;
          }
        }
        pending = merged.slice(offset);
      };
    });
  }

  /** The caller says they have finished speaking. */
  done(): void {
    this.finishListening?.();
  }

  /** Stop listening and discard what was heard (the caller chose to type). */
  cancel(): void {
    this.cancelListening?.();
  }

  /** Play a WAV prompt. Resolves when it ends or is stopped. */
  async play(data: ArrayBuffer): Promise<void> {
    if (!this.context) await this.open();
    const context = this.context!;
    if (context.state === 'suspended') await context.resume();
    const buffer = await context.decodeAudioData(data.slice(0));
    this.stopPlayback();
    await new Promise<void>((resolve) => {
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      source.onended = () => {
        if (this.playing === source) this.playing = null;
        resolve();
      };
      this.playing = source;
      source.start();
    });
  }

  stopPlayback(): void {
    const current = this.playing;
    this.playing = null;
    if (current) {
      try { current.stop(); } catch { /* already stopped */ }
    }
  }

  close(): void {
    this.cancel();
    this.stopPlayback();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.node?.disconnect();
    this.sink?.disconnect();
    void this.context?.close();
    this.context = null;
  }
}

/**
 * `useAudioRecorder()` — browser microphone recording (getUserMedia + MediaRecorder).
 *
 * Product-agnostic, no network: the consumer receives the finished Blob through
 * `onRecorded(blob, mime, seconds)` and uploads it itself.
 *
 * - mime fallback: audio/webm;codecs=opus -> audio/webm -> audio/mp4 -> audio/mpeg
 * - states: idle | requesting | recording | stopped | error
 * - auto-stop at `maxSeconds` (default 600) — delivers what was recorded
 * - size guard `maxBytes` (default 15 MB) — stops, discards, error `too_large`
 * - releases mic tracks (and the level-meter AudioContext) on stop / unmount
 * - typed errors: unsupported | permission_denied | too_large
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export type AudioRecorderState = 'idle' | 'requesting' | 'recording' | 'stopped' | 'error';
export type AudioRecorderError = 'unsupported' | 'permission_denied' | 'too_large';

export const AUDIO_MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/mpeg',
] as const;

export const DEFAULT_MAX_SECONDS = 600;
export const DEFAULT_MAX_BYTES = 15 * 1024 * 1024;

export interface UseAudioRecorderOptions {
  maxSeconds?: number;
  maxBytes?: number;
  onRecorded?: (blob: Blob, mime: string, seconds: number) => void;
}

export interface UseAudioRecorderResult {
  state: AudioRecorderState;
  error: AudioRecorderError | null;
  /** Whole seconds recorded so far. */
  seconds: number;
  /** `mm:ss` */
  elapsed: string;
  /** Input level 0..1 (0 when the Web Audio API is unavailable). */
  level: number;
  /** False when getUserMedia / MediaRecorder / a supported mime are missing. */
  supported: boolean;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

/** First mime type MediaRecorder supports; '' when none is reported (let the browser pick). null = no MediaRecorder. */
export function pickAudioMime(): string | null {
  if (typeof MediaRecorder === 'undefined') return null;
  if (typeof MediaRecorder.isTypeSupported !== 'function') return '';
  for (const m of AUDIO_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return null;
}

function isSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function' &&
    pickAudioMime() !== null
  );
}

export function useAudioRecorder(options: UseAudioRecorderOptions = {}): UseAudioRecorderResult {
  const { maxSeconds = DEFAULT_MAX_SECONDS, maxBytes = DEFAULT_MAX_BYTES } = options;
  const onRecordedRef = useRef(options.onRecorded);
  onRecordedRef.current = options.onRecorded;

  const [state, setState] = useState<AudioRecorderState>('idle');
  const [error, setError] = useState<AudioRecorderError | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const bytesRef = useRef(0);
  const startedAtRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const rafRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const failedRef = useRef<AudioRecorderError | null>(null);
  const mountedRef = useRef(true);

  const releaseResources = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    if (rafRef.current !== null && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(rafRef.current);
    }
    rafRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    const ctx = audioCtxRef.current;
    audioCtxRef.current = null;
    if (ctx) void ctx.close().catch(() => undefined);
  }, []);

  const stop = useCallback(() => {
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') rec.stop();
  }, []);

  const startLevelMeter = useCallback((stream: MediaStream) => {
    const Ctor: typeof AudioContext | undefined =
      typeof window !== 'undefined'
        ? (window.AudioContext ??
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)
        : undefined;
    if (!Ctor || typeof requestAnimationFrame !== 'function') return;
    try {
      const ctx = new Ctor();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(analyser);
      audioCtxRef.current = ctx;
      const data = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (let i = 0; i < data.length; i++) peak = Math.max(peak, Math.abs(data[i] - 128));
        if (mountedRef.current) setLevel(Math.min(1, peak / 64));
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch {
      // Level meter is cosmetic; recording works without it.
      audioCtxRef.current = null;
    }
  }, []);

  const start = useCallback(async () => {
    if (state === 'recording' || state === 'requesting') return;
    setError(null);
    setSeconds(0);
    setLevel(0);
    failedRef.current = null;
    if (!isSupported()) {
      setError('unsupported');
      setState('error');
      return;
    }
    setState('requesting');
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      if (!mountedRef.current) return;
      setError('permission_denied');
      setState('error');
      return;
    }
    if (!mountedRef.current) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    streamRef.current = stream;
    chunksRef.current = [];
    bytesRef.current = 0;

    const picked = pickAudioMime();
    let rec: MediaRecorder;
    try {
      rec = picked ? new MediaRecorder(stream, { mimeType: picked }) : new MediaRecorder(stream);
    } catch {
      releaseResources();
      setError('unsupported');
      setState('error');
      return;
    }
    recorderRef.current = rec;

    rec.ondataavailable = (ev: BlobEvent) => {
      if (!ev.data || ev.data.size === 0) return;
      chunksRef.current.push(ev.data);
      bytesRef.current += ev.data.size;
      if (bytesRef.current > maxBytes && !failedRef.current) {
        failedRef.current = 'too_large';
        stop();
      }
    };
    rec.onstop = () => {
      const elapsedSec = Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000));
      const mime = rec.mimeType || picked || 'audio/webm';
      const chunks = chunksRef.current;
      chunksRef.current = [];
      releaseResources();
      recorderRef.current = null;
      if (!mountedRef.current) return;
      setLevel(0);
      if (failedRef.current) {
        setError(failedRef.current);
        setState('error');
        return;
      }
      setSeconds(elapsedSec);
      setState('stopped');
      onRecordedRef.current?.(new Blob(chunks, { type: mime }), mime, elapsedSec);
    };

    startedAtRef.current = Date.now();
    rec.start(1000);
    setState('recording');
    startLevelMeter(stream);
    timerRef.current = setInterval(() => {
      const s = Math.floor((Date.now() - startedAtRef.current) / 1000);
      if (mountedRef.current) setSeconds(s);
      if (s >= maxSeconds) stop();
    }, 250);
  }, [state, maxBytes, maxSeconds, releaseResources, startLevelMeter, stop]);

  const reset = useCallback(() => {
    setState('idle');
    setError(null);
    setSeconds(0);
    setLevel(0);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const rec = recorderRef.current;
      if (rec) {
        rec.ondataavailable = null;
        rec.onstop = null;
        if (rec.state !== 'inactive') rec.stop();
      }
      recorderRef.current = null;
      releaseResources();
    };
  }, [releaseResources]);

  return {
    state,
    error,
    seconds,
    elapsed: formatElapsed(seconds),
    level,
    supported: typeof window === 'undefined' ? true : isSupported(),
    start,
    stop,
    reset,
  };
}

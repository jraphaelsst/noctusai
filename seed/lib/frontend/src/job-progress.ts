/**
 * `useJobProgress` — a job's progress PUSHED over SSE into the TanStack cache, polling only as the fallback.
 *
 * Browser half of `noctusai_lib.realtime.job_progress` (`KB § PATTERNS/common/realtime-sse-bus.md` § Job
 * progress). A long job used to hand off to `jobPolling` (every open tab re-reads every 2-5 s for minutes).
 * With a stream, the server pushes `{status, progress, stage, message, terminal}` and this hook:
 *   1. writes each update into the cache entries the job touches (`targets[].update` → `setQueryData`);
 *   2. tells `jobPolling` the stream is live (`markJobStreamLive`), so the read does NOT also poll;
 *   3. on the terminal frame, refreshes the authoritative read once (`invalidateQueries`) and closes;
 *   4. if the stream cannot be kept (refused / 401 / proxy killed it) for `fallbackAfterMs`, releases the
 *      live mark and calls `handOffToPolling(qc, readKey)` — the pre-existing polling path takes over.
 *
 * The read still spreads `jobPolling(...)` (it IS the fallback), and a job-starting write still hands off
 * with `handOffToPolling` — that is what covers the gap before the stream opens and the fallback. Keeper
 * `check_job_start_without_handoff` accepts that shape; the stream is an optimisation over it, never a
 * replacement for it.
 *
 * ```ts
 * const { progress, mode } = useJobProgress({
 *   jobId, url: `/api/media-creation/headlines/lotes/${jobId}/progress`, getAuthToken,
 *   readKey: loteKey(jobId),
 *   targets: [{ queryKey: loteKey(jobId), update: (prev, p) => prev && { ...prev, etapa: p.stage } }],
 * });
 * ```
 */
import { useEffect, useRef, useState } from "react";
import { useQueryClient, type QueryKey } from "@tanstack/react-query";

import {
  handOffToPolling,
  markJobStreamLive,
  type HandOffQueryClient,
  type HandOffToPollingOptions,
} from "./job-polling";
import { useRealtimeStream, type RealtimeMessage } from "./realtime";

export const JOB_PROGRESS_EVENT = "job.progress";
export const JOB_PROGRESS_FALLBACK_MS = 8_000;

/** The payload of one `job.progress` frame (see `JobProgress.to_payload`). */
export interface JobProgressState {
  status: string;
  /** 0..1, or null when the job cannot say. */
  progress: number | null;
  stage: string | null;
  message: string | null;
  terminal: boolean;
}

export interface JobProgressTarget<TData = unknown> {
  queryKey: QueryKey;
  /** Fold the update into the cached value; return `undefined` to leave the entry untouched. */
  update: (prev: TData | undefined, progress: JobProgressState) => TData | undefined;
}

export type JobProgressMode = "idle" | "stream" | "polling" | "done";

export interface UseJobProgressOptions {
  /** `null` disables the hook (no job yet). */
  jobId: string | null;
  /** Fully-qualified stream endpoint of THIS job. */
  url: string | null;
  getAuthToken: () => Promise<string | null>;
  /** The polled read (`jobPolling`) of this job: released while the stream is live, handed off to on fallback / terminal. */
  readKey: QueryKey;
  /** Cache entries the job's progress is written into. */
  targets?: JobProgressTarget<any>[];
  enabled?: boolean;
  /** How long the stream may stay down before falling back to polling. Default 8 s. */
  fallbackAfterMs?: number;
  handOff?: HandOffToPollingOptions;
}

/**
 * The job-STARTING write's hand-off for a read that has a progress stream: identical to
 * `handOffToPolling` on purpose. Until the stream opens (and whenever it cannot) the read polls;
 * `useJobProgress` marks the read live when the stream opens, which silences that poll, and releases it
 * if the stream drops. The distinct name tells the keeper (`check_job_start_without_handoff`) and the
 * reader that this job is PUSHED first, polled only as the fallback.
 */
export function handOffToJobProgress(
  qc: HandOffQueryClient,
  readKey: QueryKey,
  options?: HandOffToPollingOptions,
): Promise<void> {
  return handOffToPolling(qc, readKey, options);
}

/**
 * Fold a frame into the last state. Terminal is final; progress never moves backwards (a snapshot taken
 * a moment before a replayed older event must not make the bar jump back).
 */
export function mergeJobProgress(prev: JobProgressState | null, next: JobProgressState): JobProgressState {
  if (!prev) return next;
  if (prev.terminal) return prev;
  if (!next.terminal && prev.progress != null && next.progress != null && next.progress < prev.progress) {
    return { ...next, progress: prev.progress };
  }
  return next;
}

export function useJobProgress(options: UseJobProgressOptions): {
  progress: JobProgressState | null;
  mode: JobProgressMode;
} {
  const { jobId, url, getAuthToken, readKey, enabled = true, fallbackAfterMs = JOB_PROGRESS_FALLBACK_MS } = options;
  const qc = useQueryClient();
  const [progress, setProgress] = useState<JobProgressState | null>(null);
  const [fellBack, setFellBack] = useState(false);
  const progressRef = useRef<JobProgressState | null>(null);
  const targetsRef = useRef(options.targets);
  targetsRef.current = options.targets;
  const handOffRef = useRef(options.handOff);
  handOffRef.current = options.handOff;
  const readKeyHash = JSON.stringify(readKey);

  // A different job starts clean.
  useEffect(() => {
    progressRef.current = null;
    setProgress(null);
    setFellBack(false);
  }, [jobId]);

  // The same job running AGAIN (a re-run): the caller re-enables the hook, so a stale terminal state must not block it.
  useEffect(() => {
    if (enabled && progressRef.current?.terminal) {
      progressRef.current = null;
      setProgress(null);
      setFellBack(false);
    }
  }, [enabled]);

  const done = progress?.terminal === true;
  const active = !!jobId && !!url && enabled && !fellBack && !done;

  const onEvent = (message: RealtimeMessage) => {
    if (message.event !== JOB_PROGRESS_EVENT) return;
    const next = mergeJobProgress(progressRef.current, message.payload as unknown as JobProgressState);
    if (next === progressRef.current) return;
    progressRef.current = next;
    setProgress(next);
    for (const t of targetsRef.current ?? []) {
      qc.setQueryData(t.queryKey, (prev: unknown) => t.update(prev, next));
    }
    // The terminal frame carries no result data: the authoritative read does.
    if (next.terminal) void qc.invalidateQueries({ queryKey: readKey });
  };

  const { status } = useRealtimeStream(active ? url : null, {
    getAuthToken,
    events: [JOB_PROGRESS_EVENT],
    onEvent,
  });

  // Push replaces the poll only while the stream is actually open.
  useEffect(() => {
    if (!active || status !== "open") return;
    return markJobStreamLive(readKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, status, readKeyHash]);

  // The stream cannot be kept: hand the job back to polling.
  useEffect(() => {
    if (!active || status === "open") return;
    const timer = setTimeout(() => {
      setFellBack(true);
      void handOffToPolling(qc, readKey, handOffRef.current);
    }, fallbackAfterMs);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, status, fallbackAfterMs, readKeyHash, qc]);

  const mode: JobProgressMode = !jobId || !url || !enabled ? "idle" : done ? "done" : fellBack ? "polling" : "stream";
  return { progress, mode };
}

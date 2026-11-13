/**
 * `uploadResumable` — chunked, resumable upload against the seed `resumable_uploads` backend seam.
 *
 * Why: a large file in ONE request restarts from zero on a dropped mobile connection and its progress bar lies.
 * Here the file is cut into parts (size chosen by the server), sent 4 at a time; a failed part is retried with
 * exponential backoff; the SERVER says which parts it already holds (`GET {basePath}/{id}`), so calling again with
 * the same `clientKey` re-sends only the missing ones. Progress counts server-CONFIRMED parts only.
 *
 * Secrets never reach the client: it only talks to our own endpoints (the session is org + prefix scoped server-side).
 */
import { ApiError } from './api';
import type { ApiClient } from './api';

export const RESUMABLE_UPLOAD_BASE_PATH = '/api/uploads';
export const RESUMABLE_UPLOAD_CONCURRENCY = 4;

export type UploadApi = Pick<ApiClient, 'get' | 'post' | 'delete' | 'putRaw'>;

export interface UploadSessionDto {
  id: string;
  status: string;
  filename: string;
  size_bytes: number;
  part_size: number;
  total_parts: number;
  object_key: string | null;
  /** Part numbers (1-based) the server already holds. */
  parts: number[];
}

export interface UploadProgress {
  confirmedBytes: number;
  totalBytes: number;
  confirmedParts: number;
  totalParts: number;
  /** 0-100, from confirmed parts only (an in-flight part counts for nothing). */
  percent: number;
}

export interface ResumableUploadOptions {
  basePath?: string;
  concurrency?: number;
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** Stable id of "this file" so a re-run resumes the same server session. Default: name+size+lastModified. */
  clientKey?: string;
  signal?: AbortSignal;
  onProgress?: (p: UploadProgress) => void;
  /** Injectable for tests. */
  sleep?: (ms: number) => Promise<void>;
}

export interface ResumableUploadResult {
  uploadId: string;
  objectKey: string;
  session: UploadSessionDto;
}

/** Thrown when a part exhausted its retries. The session survives: call `uploadResumable` again to resume. */
export class ResumableUploadError extends Error {
  readonly resumable: boolean;
  readonly uploadId?: string;
  constructor(message: string, opts: { resumable: boolean; uploadId?: string; cause?: unknown }) {
    super(message);
    this.name = 'ResumableUploadError';
    this.resumable = opts.resumable;
    this.uploadId = opts.uploadId;
    if (opts.cause !== undefined) (this as { cause?: unknown }).cause = opts.cause;
  }
}

/** Retry only what can heal: network errors, timeouts, 408/425/429 and 5xx. 4xx (bad part, expired, gone) is final. */
export function isRetryableUploadError(err: unknown): boolean {
  if (err instanceof ApiError) {
    const s = err.status;
    return s === null || s === 408 || s === 425 || s === 429 || s >= 500;
  }
  return !(err instanceof DOMException && err.name === 'AbortError');
}

export function backoffDelayMs(attempt: number, base: number, max: number): number {
  return Math.min(max, base * 2 ** attempt);
}

const realSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export function defaultClientKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export async function uploadResumable(
  api: UploadApi,
  file: File,
  options: ResumableUploadOptions = {},
): Promise<ResumableUploadResult> {
  const {
    basePath = RESUMABLE_UPLOAD_BASE_PATH,
    concurrency = RESUMABLE_UPLOAD_CONCURRENCY,
    maxRetries = 5,
    baseDelayMs = 500,
    maxDelayMs = 15_000,
    signal,
    onProgress,
    sleep = realSleep,
  } = options;
  if (!api.putRaw) throw new Error('uploadResumable: this ApiClient has no putRaw (use createApiClient)');
  const putRaw = api.putRaw.bind(api);

  const session = await api.post<UploadSessionDto>(basePath, {
    filename: file.name,
    content_type: file.type || 'application/octet-stream',
    size_bytes: file.size,
    client_key: options.clientKey ?? defaultClientKey(file),
  });
  const { id, part_size: partSize, total_parts: total } = session;
  const confirmed = new Set<number>(session.parts);

  const partLen = (n: number) => (n < total ? partSize : file.size - partSize * (total - 1));
  const report = () => {
    let bytes = 0;
    confirmed.forEach((n) => (bytes += partLen(n)));
    onProgress?.({
      confirmedBytes: bytes,
      totalBytes: file.size,
      confirmedParts: confirmed.size,
      totalParts: total,
      percent: file.size ? Math.floor((bytes / file.size) * 100) : 100,
    });
  };
  report();

  const sendPart = async (n: number) => {
    const blob = file.slice((n - 1) * partSize, (n - 1) * partSize + partLen(n));
    for (let attempt = 0; ; attempt++) {
      if (signal?.aborted) throw new DOMException('aborted', 'AbortError');
      try {
        await putRaw(`${basePath}/${id}/parts/${n}`, blob, { signal });
        confirmed.add(n);
        report();
        return;
      } catch (err) {
        if (attempt >= maxRetries || !isRetryableUploadError(err)) throw err;
        await sleep(backoffDelayMs(attempt, baseDelayMs, maxDelayMs));
      }
    }
  };

  const sendAll = async (numbers: number[]) => {
    const queue = [...numbers];
    let failure: unknown;
    const worker = async () => {
      while (failure === undefined) {
        const n = queue.shift();
        if (n === undefined) return;
        try {
          await sendPart(n);
        } catch (err) {
          failure = err;
        }
      }
    };
    await Promise.all(Array.from({ length: Math.max(1, concurrency) }, worker));
    if (failure !== undefined) throw failure;
  };

  const fail = (err: unknown): never => {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    const fatal = err instanceof ApiError && !isRetryableUploadError(err);
    throw new ResumableUploadError(
      err instanceof Error ? err.message : 'Falha no envio',
      { resumable: !fatal, uploadId: id, cause: err },
    );
  };

  try {
    const pending = Array.from({ length: total }, (_, i) => i + 1).filter((n) => !confirmed.has(n));
    await sendAll(pending);
    for (let round = 0; ; round++) {
      try {
        const done = await api.post<UploadSessionDto>(`${basePath}/${id}/complete`);
        return { uploadId: id, objectKey: done.object_key ?? '', session: done };
      } catch (err) {
        const missing = err instanceof ApiError && err.status === 409 ? (err.field('missing') as number[] | undefined) : undefined;
        if (!missing || missing.length === 0 || round >= 2) throw err;
        missing.forEach((n) => confirmed.delete(n));
        await sendAll(missing);
      }
    }
  } catch (err) {
    return fail(err);
  }
}

/** Abort the server session (drops its parts). Best effort: a 404 means it is already gone. */
export async function abortResumableUpload(api: UploadApi, uploadId: string, basePath = RESUMABLE_UPLOAD_BASE_PATH) {
  try {
    await api.delete(`${basePath}/${uploadId}`);
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 404)) throw err;
  }
}

import { describe, expect, it } from 'vitest';
import { ApiError } from './api';
import { uploadResumable, ResumableUploadError, backoffDelayMs, isRetryableUploadError } from './resumableUpload';
import type { UploadApi, UploadProgress, UploadSessionDto } from './resumableUpload';

const PART = 10;
const mkFile = (n: number) => new File([new Uint8Array(n)], 'v.mp4', { type: 'video/mp4', lastModified: 1 });
const err = (status: number, body: unknown = {}) => new ApiError(status, 'x', body);

/** In-memory server: remembers parts across `uploadResumable` calls (a "reconnect"). */
function server(opts: { failures?: Record<number, number>; hooks?: (n: number) => void } = {}) {
  const parts = new Set<number>();
  const sent: number[] = [];
  const failures = { ...(opts.failures ?? {}) };
  let inFlight = 0;
  let maxInFlight = 0;
  const total = (size: number) => Math.ceil(size / PART);
  let size = 0;
  const dto = (extra: Partial<UploadSessionDto> = {}): UploadSessionDto => ({
    id: 'u1', status: 'open', filename: 'v.mp4', size_bytes: size, part_size: PART, total_parts: total(size),
    object_key: null, parts: [...parts].sort((a, b) => a - b), ...extra,
  });
  const api: UploadApi = {
    get: async () => dto(),
    delete: async () => ({}),
    post: (async (path: string, body?: any) => {
      if (path.endsWith('/complete')) {
        const missing = Array.from({ length: total(size) }, (_, i) => i + 1).filter((n) => !parts.has(n));
        if (missing.length) throw err(409, { detail: { missing } });
        return dto({ status: 'completed', object_key: 'org/u1/v.mp4' });
      }
      size = body.size_bytes;
      return dto();
    }) as any,
    putRaw: (async (path: string, blob: Blob, o?: { signal?: AbortSignal }) => {
      const n = Number(path.split('/').pop());
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      try {
        await Promise.resolve();
        if (failures[n]) {
          failures[n]--;
          throw err(503);
        }
        expect(blob.size).toBe(n < total(size) ? PART : size - PART * (total(size) - 1));
        sent.push(n);
        parts.add(n);
        opts.hooks?.(n);
        return { number: n };
      } finally {
        inFlight--;
      }
    }) as any,
  };
  return { api, parts, sent, failures, maxInFlight: () => maxInFlight };
}

const fast = { sleep: async () => {}, baseDelayMs: 0 };

describe('uploadResumable', () => {
  it('uploads in parts, 4 at a time, and completes', async () => {
    const s = server();
    const res = await uploadResumable(s.api, mkFile(95), fast); // 10 parts
    expect(res.objectKey).toBe('org/u1/v.mp4');
    expect(s.sent.sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(s.maxInFlight()).toBeLessThanOrEqual(4);
    expect(s.maxInFlight()).toBeGreaterThan(1);
  });

  it('retries a failed part with backoff and still completes', async () => {
    const s = server({ failures: { 2: 3 } });
    const sleeps: number[] = [];
    await uploadResumable(s.api, mkFile(30), { sleep: async (ms) => void sleeps.push(ms), baseDelayMs: 100 });
    expect(sleeps).toEqual([100, 200, 400]);
    expect(s.parts.size).toBe(3);
  });

  it('after giving up, a re-run sends ONLY the missing parts (server-reported)', async () => {
    const s = server({ failures: { 3: 99 } });
    await expect(uploadResumable(s.api, mkFile(40), { ...fast, maxRetries: 1 })).rejects.toBeInstanceOf(ResumableUploadError);
    expect(s.parts.has(3)).toBe(false);
    const had = new Set(s.parts);
    s.sent.length = 0;
    s.failures[3] = 0; // the network heals; the user taps "retry" -> same file, same clientKey
    await uploadResumable(s.api, mkFile(40), fast);
    expect(s.sent).toEqual([3]);
    expect(had.size).toBe(3);
  });

  it('progress counts confirmed parts only and never exceeds the truth', async () => {
    const s = server();
    const seen: UploadProgress[] = [];
    await uploadResumable(s.api, mkFile(40), { ...fast, concurrency: 1, onProgress: (p) => seen.push(p) });
    expect(seen[0].percent).toBe(0);
    expect(seen.map((p) => p.confirmedParts)).toEqual([0, 1, 2, 3, 4]);
    expect(seen[seen.length - 1].percent).toBe(100);
  });

  it('does not retry a final 4xx (expired/invalid) and flags it non-resumable', async () => {
    const s = server();
    s.api.putRaw = (async () => {
      throw err(410);
    }) as any;
    const p = uploadResumable(s.api, mkFile(20), fast);
    await expect(p).rejects.toMatchObject({ resumable: false });
  });

  it('classifies retryable errors', () => {
    expect(isRetryableUploadError(err(503))).toBe(true);
    expect(isRetryableUploadError(err(429))).toBe(true);
    expect(isRetryableUploadError(err(422))).toBe(false);
    expect(isRetryableUploadError(new TypeError('Failed to fetch'))).toBe(true);
    expect(backoffDelayMs(10, 500, 15000)).toBe(15000);
  });
});

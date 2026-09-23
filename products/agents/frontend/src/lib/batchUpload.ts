/**
 * Generic chunk-and-send orchestration for the Studio batch upload routes
 * (Conhecimento documents, Skill reference files — CONTRACT.md §G items
 * 1/2). Framework-agnostic — no React — so it is unit-testable without a
 * DOM and reusable by both dialogs.
 *
 * A batch route caps how many items AND how many bytes one call accepts
 * (documents: 100 items / 20 MB, skill files: 50 items / 8 MB —
 * `@/api/studio/batchPaths.ts`, confirmed against the landed backend), so a
 * large upload (the audit's worked example: 382 knowledge documents) is
 * split into sequential chunk calls that respect BOTH caps — item count is
 * the binding limit for realistic markdown documents, but a chunk that
 * would exceed the byte cap first is still split early rather than sent
 * and 422'd. "Sequential" matters twice over: the backend route is per-call
 * bounded, and a failed chunk must never abandon the rest of the upload
 * (§G item 1) — each chunk's own outcome (resolved response OR thrown
 * error, e.g. skill files' whole-call 409 `version_immutable`) is recorded
 * and the loop always continues to the next chunk, never short-circuiting
 * on either shape of failure.
 */

export interface ChunkLimits {
  /** Max items per chunk. */
  maxCount: number;
  /** Max total (approximate) byte size per chunk. */
  maxBytes: number;
}

const encoder = new TextEncoder();

/** Approximate wire size of one item — `JSON.stringify` UTF-8 byte length. */
export function byteSizeOf(item: unknown): number {
  return encoder.encode(JSON.stringify(item)).length;
}

/**
 * Splits `items` into consecutive chunks, each holding at most
 * `limits.maxCount` items and at most `limits.maxBytes` total (per
 * `sizeOf`, default `byteSizeOf`). A single item larger than `maxBytes` on
 * its own still gets a chunk of its own (never split mid-item, never
 * dropped) — the batch route rejecting that chunk is a real, surfaceable
 * failure, not something client-side chunking can silently fix.
 */
export function chunkBySizeAndCount<T>(items: T[], limits: ChunkLimits, sizeOf: (item: T) => number = byteSizeOf): T[][] {
  const { maxCount, maxBytes } = limits;
  if (maxCount <= 0) throw new Error("maxCount must be positive");
  const out: T[][] = [];
  let current: T[] = [];
  let currentBytes = 0;
  for (const item of items) {
    const itemBytes = sizeOf(item);
    const exceedsCount = current.length + 1 > maxCount;
    const exceedsBytes = current.length > 0 && currentBytes + itemBytes > maxBytes;
    if (current.length > 0 && (exceedsCount || exceedsBytes)) {
      out.push(current);
      current = [];
      currentBytes = 0;
    }
    current.push(item);
    currentBytes += itemBytes;
  }
  if (current.length > 0) out.push(current);
  return out;
}

export interface ChunkSuccess<R> {
  index: number;
  items: unknown[];
  ok: true;
  response: R;
}

export interface ChunkFailure {
  index: number;
  items: unknown[];
  ok: false;
  error: unknown;
}

export type ChunkResult<R> = ChunkSuccess<R> | ChunkFailure;

/** Narrows a `ChunkResult` — `"error" in cr"` reads correctly under this
 * project's `strictNullChecks: false` where a plain `if (cr.ok)` does NOT
 * narrow a generic discriminated union (verified: TS2339 on the `else`
 * branch without this). Exported so callers use the same guard. */
export function chunkFailed<R>(cr: ChunkResult<R>): cr is ChunkFailure {
  return "error" in cr;
}

/**
 * Sends `items` to `send` in chunks respecting `limits` (never in parallel
 * — a batch route processes one call at a time server-side, and a progress
 * indicator needs the calls to resolve in order). Every chunk's outcome
 * lands in the returned array regardless of whether `send` resolved or
 * threw, and `onProgress` fires after each chunk with the running count of
 * items sent — so callers can render "enviando 200/382…".
 */
export async function sendInChunks<T, R>(
  items: T[],
  limits: ChunkLimits,
  send: (batch: T[]) => Promise<R>,
  onProgress?: (sent: number, total: number) => void,
  sizeOf?: (item: T) => number,
): Promise<ChunkResult<R>[]> {
  const chunks = chunkBySizeAndCount(items, limits, sizeOf);
  const results: ChunkResult<R>[] = [];
  let sent = 0;
  for (let i = 0; i < chunks.length; i++) {
    const batch = chunks[i];
    try {
      const response = await send(batch);
      results.push({ index: i, items: batch, ok: true, response });
    } catch (error) {
      results.push({ index: i, items: batch, ok: false, error });
    }
    sent += batch.length;
    onProgress?.(sent, items.length);
  }
  return results;
}

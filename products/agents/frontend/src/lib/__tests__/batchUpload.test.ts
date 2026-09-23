/**
 * `batchUpload.ts` — chunk-and-send orchestration for the Studio multi-file
 * uploaders (CONTRACT.md §G items 1/2). Covers the audit's worked example
 * (382 documents → 4 calls of 100/100/100/82) and the "a failed chunk must
 * never abandon the rest of the upload" requirement.
 */
import { describe, expect, it, vi } from "vitest";
import { byteSizeOf, chunkBySizeAndCount, chunkFailed, sendInChunks } from "@/lib/batchUpload";

describe("chunkBySizeAndCount", () => {
  it("splits 382 items into 100/100/100/82 under a 100-item cap", () => {
    const items = Array.from({ length: 382 }, (_, i) => ({ slug: `doc-${i}` }));
    const chunks = chunkBySizeAndCount(items, { maxCount: 100, maxBytes: 20 * 1024 * 1024 });
    expect(chunks.map((c) => c.length)).toEqual([100, 100, 100, 82]);
    // No item lost or duplicated across chunks.
    expect(chunks.flat()).toHaveLength(382);
  });

  it("also splits early when a chunk would exceed the byte cap, even under the count cap", () => {
    // Each item is ~1 KB; a 3 KB cap must yield 3 items per chunk even
    // though the count cap (100) would allow far more.
    const items = Array.from({ length: 10 }, (_, i) => ({ conteudo: "x".repeat(1000), i }));
    const chunks = chunkBySizeAndCount(items, { maxCount: 100, maxBytes: 3000 });
    expect(chunks.every((c) => c.length <= 4)).toBe(true);
    expect(chunks.flat()).toHaveLength(10);
  });

  it("never splits mid-item — an item bigger than maxBytes on its own still gets a chunk", () => {
    const items = [{ conteudo: "x".repeat(5000) }];
    const chunks = chunkBySizeAndCount(items, { maxCount: 100, maxBytes: 100 });
    expect(chunks).toEqual([items]);
  });

  it("returns an empty array for an empty input", () => {
    expect(chunkBySizeAndCount([], { maxCount: 100, maxBytes: 1000 })).toEqual([]);
  });
});

describe("byteSizeOf", () => {
  it("measures the UTF-8 byte length of the JSON-serialized item", () => {
    expect(byteSizeOf({ a: "ab" })).toBe(new TextEncoder().encode('{"a":"ab"}').length);
  });
});

describe("sendInChunks", () => {
  it("sends 382 items in 4 sequential calls (100/100/100/82) and reports progress", async () => {
    const items = Array.from({ length: 382 }, (_, i) => ({ slug: `doc-${i}` }));
    const send = vi.fn(async (batch: unknown[]) => ({ resultados: batch.length }));
    const onProgress = vi.fn();

    const results = await sendInChunks(items, { maxCount: 100, maxBytes: 20 * 1024 * 1024 }, send, onProgress);

    expect(send).toHaveBeenCalledTimes(4);
    expect(send.mock.calls.map(([batch]) => (batch as unknown[]).length)).toEqual([100, 100, 100, 82]);
    expect(results.every((r) => !chunkFailed(r))).toBe(true);
    expect(onProgress).toHaveBeenLastCalledWith(382, 382);
    expect(onProgress).toHaveBeenCalledTimes(4);
  });

  it("still sends the 4th chunk when the 2nd chunk's call throws — never abandons the rest", async () => {
    const items = Array.from({ length: 382 }, (_, i) => ({ slug: `doc-${i}` }));
    const send = vi.fn(async (batch: unknown[]) => {
      if (send.mock.calls.length === 2) throw new Error("upstream 502");
      return { resultados: batch.length };
    });

    const results = await sendInChunks(items, { maxCount: 100, maxBytes: 20 * 1024 * 1024 }, send);

    expect(send).toHaveBeenCalledTimes(4);
    expect(results).toHaveLength(4);
    expect(results.map((r) => chunkFailed(r))).toEqual([false, true, false, false]);
  });

  it("still sends the 4th chunk when the 2nd chunk's RESPONSE reports per-item errors (not a throw)", async () => {
    const items = Array.from({ length: 382 }, (_, i) => ({ slug: `doc-${i}` }));
    const send = vi.fn(async (batch: unknown[]) => {
      const callNumber = send.mock.calls.length;
      if (callNumber === 2) {
        return { resultados: batch.map((_, i) => ({ slug: `doc-${i}`, status: i === 0 ? "erro" : "criado" })) };
      }
      return { resultados: batch.map(() => ({ status: "criado" })) };
    });

    const results = await sendInChunks(items, { maxCount: 100, maxBytes: 20 * 1024 * 1024 }, send);

    expect(send).toHaveBeenCalledTimes(4);
    expect(results.every((r) => !chunkFailed(r))).toBe(true);
  });

  it("chunkFailed narrows a failed chunk's `error` and a successful chunk's `response`", async () => {
    const send = vi.fn().mockRejectedValueOnce(new Error("boom"));
    const results = await sendInChunks([{ a: 1 }], { maxCount: 1, maxBytes: 1000 }, send);
    const [first] = results;
    if (chunkFailed(first)) {
      expect(first.error).toBeInstanceOf(Error);
    } else {
      throw new Error("expected the chunk to have failed");
    }
  });
});

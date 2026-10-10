import { describe, expect, it } from "vitest";
import { readSseStream } from "./readSseStream";

const enc = new TextEncoder();

function responseOf(chunks: string[], opts: { hang?: boolean } = {}): Response {
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(enc.encode(chunks[i++]));
      } else if (!opts.hang) {
        controller.close();
      }
    },
  });
  return new Response(stream);
}

async function collect<T>(it: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const f of it) out.push(f);
  return out;
}

describe("readSseStream", () => {
  it("yields one payload per frame", async () => {
    const res = responseOf(['data: {"delta":"a"}\n\ndata: {"delta":"b"}\n\n']);
    expect(await collect(readSseStream(res))).toEqual([{ delta: "a" }, { delta: "b" }]);
  });

  it("reassembles frames split across chunks (even mid-UTF-8 and mid-separator)", async () => {
    const full = enc.encode('data: {"delta":"olá"}\n\ndata: {"delta":"x"}\n\n');
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(full.slice(0, 20)); // inside the first frame, splits "á"
        c.enqueue(full.slice(20, 24));
        c.enqueue(full.slice(24));
        c.close();
      },
    });
    const frames = await collect(readSseStream(new Response(stream)));
    expect(frames).toEqual([{ delta: "olá" }, { delta: "x" }]);
  });

  it("joins multi-line data fields of one frame", async () => {
    const res = responseOf(['data: {"a":\ndata: 1}\n\n']);
    expect(await collect(readSseStream(res))).toEqual([{ a: 1 }]);
  });

  it("drops malformed and non-data frames, keeps going", async () => {
    const res = responseOf([': ping\n\ndata: not-json\n\ndata: {"ok":true}\n\n']);
    expect(await collect(readSseStream(res))).toEqual([{ ok: true }]);
  });

  it("delivers an error frame as a normal payload", async () => {
    const res = responseOf(['data: {"error":{"code":"ia_nao_configurada","message":"x"}}\n\n']);
    const frames = await collect(readSseStream<{ error?: { code: string } }>(res));
    expect(frames[0].error?.code).toBe("ia_nao_configurada");
  });

  it("flushes a final frame lacking the trailing blank line", async () => {
    const res = responseOf(['data: {"done":true}']);
    expect(await collect(readSseStream(res))).toEqual([{ done: true }]);
  });

  it("throws AbortError when aborted mid-stream", async () => {
    const ac = new AbortController();
    const res = responseOf(['data: {"n":1}\n\n'], { hang: true });
    const seen: unknown[] = [];
    const run = (async () => {
      for await (const f of readSseStream(res, { signal: ac.signal })) {
        seen.push(f);
        ac.abort();
      }
    })();
    await expect(run).rejects.toMatchObject({ name: "AbortError" });
    expect(seen).toEqual([{ n: 1 }]);
  });

  it("throws AbortError immediately for an already-aborted signal", async () => {
    const ac = new AbortController();
    ac.abort();
    await expect(
      collect(readSseStream(responseOf(["data: {}\n\n"]), { signal: ac.signal })),
    ).rejects.toMatchObject({ name: "AbortError" });
  });

  it("throws when the response has no body", async () => {
    await expect(collect(readSseStream(new Response(null)))).rejects.toThrow(/Streaming/);
  });
});

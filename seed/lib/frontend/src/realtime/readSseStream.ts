/**
 * readSseStream — typed, abortable reader for `data: <json>` SSE frames over a
 * `fetch` Response body (POST-able, so not `EventSource`).
 *
 * Frame format (shared by help_chat and the CoreStudio chat): frames are
 * separated by a blank line (`\n\n`); each frame's `data: ` line(s) carry JSON.
 * Multi-line `data:` fields of one frame are joined with `\n` (SSE spec) before
 * parsing. A frame that is not valid JSON is dropped, never fatal. Non-`data:`
 * lines (comments, `event:`, `id:`) are ignored.
 *
 * Usage:
 *   for await (const frame of readSseStream<{ delta?: string }>(res, { signal })) { ... }
 *
 * Abort: when `signal` aborts, the underlying reader is cancelled and the
 * iterator throws an `AbortError` (same `name` fetch itself uses).
 * Error frames are NOT special-cased — they are payloads like any other; the
 * caller decides (e.g. `if (frame.error)`).
 */
export interface ReadSseStreamOptions {
  signal?: AbortSignal;
}

function abortError(): Error {
  const err = new Error("The operation was aborted.");
  err.name = "AbortError";
  return err;
}

/** Parse one raw frame into its JSON payload, or `undefined` if it carries none. */
function parseFrame<T>(frame: string): T | undefined {
  const dataLines: string[] = [];
  for (const raw of frame.split("\n")) {
    const line = raw.replace(/\r$/, "");
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
  }
  if (dataLines.length === 0) return undefined;
  try {
    return JSON.parse(dataLines.join("\n")) as T;
  } catch {
    return undefined; // malformed frame: dropped, not fatal to the stream
  }
}

export async function* readSseStream<T = unknown>(
  response: Response,
  options: ReadSseStreamOptions = {},
): AsyncGenerator<T, void, undefined> {
  const { signal } = options;
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Streaming não é suportado neste navegador.");
  }
  const decoder = new TextDecoder();
  let buffer = "";

  const onAbort = () => {
    void reader.cancel().catch(() => undefined);
  };
  if (signal?.aborted) {
    onAbort();
    throw abortError();
  }
  signal?.addEventListener("abort", onAbort, { once: true });

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (signal?.aborted) throw abortError();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.replace(/\r\n/g, "\n").split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const payload = parseFrame<T>(frame);
        if (payload !== undefined) yield payload;
      }
    }
    buffer += decoder.decode();
    const tail = parseFrame<T>(buffer.replace(/\r\n/g, "\n"));
    if (tail !== undefined) yield tail;
  } finally {
    signal?.removeEventListener("abort", onAbort);
    void reader.cancel().catch(() => undefined);
  }
}

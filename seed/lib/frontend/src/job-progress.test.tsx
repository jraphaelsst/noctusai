/**
 * useJobProgress — SSE push for one job: writes each update into the cache entries the job touches,
 * stops the read's polling while the stream is live, closes on the terminal frame, and FALLS BACK to the
 * polling hand-off when the stream cannot be kept.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { jobPolling, resetJobHandOffs, resetJobStreams } from "./job-polling";
import { mergeJobProgress, useJobProgress, type JobProgressState } from "./job-progress";

type Job = { id: string; status: string; progress: number };
const READ = ["thing", "job", "j1"] as const;

function sse(frames: string[], opts: { ok?: boolean; status?: number; hang?: boolean } = {}) {
  const enc = new TextEncoder();
  let i = 0;
  return {
    ok: opts.ok ?? true,
    status: opts.status ?? 200,
    body: {
      getReader: () => ({
        read: async () => {
          if (i < frames.length) return { done: false, value: enc.encode(frames[i++]) };
          if (opts.hang) return new Promise(() => {});
          return { done: true, value: undefined };
        },
      }),
    },
  };
}
const frame = (p: Partial<JobProgressState>) =>
  `event: job.progress\ndata: ${JSON.stringify({ status: "processando", progress: 0, stage: null, message: null, terminal: false, ...p })}\n\n`;

let qc: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client: qc }, children);

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(READ, { id: "j1", status: "processando", progress: 0 } satisfies Job);
  vi.stubGlobal("fetch", vi.fn());
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
  resetJobHandOffs();
  resetJobStreams();
});

const base = {
  jobId: "j1",
  url: "/api/x/jobs/j1",
  getAuthToken: async () => "jwt",
  readKey: READ,
  targets: [
    {
      queryKey: READ,
      update: (prev: Job | undefined, p: JobProgressState): Job | undefined =>
        prev && { ...prev, status: p.status, progress: Math.round((p.progress ?? 0) * 100) },
    },
  ],
};

describe("mergeJobProgress", () => {
  const run = (progress: number): JobProgressState => ({ status: "processando", progress, stage: null, message: null, terminal: false });
  it("never moves progress backwards on a replayed/older frame", () => {
    expect(mergeJobProgress(run(0.6), run(0.2)).progress).toBe(0.6);
    expect(mergeJobProgress(run(0.2), run(0.6)).progress).toBe(0.6);
  });
  it("a terminal state is final", () => {
    const done = { ...run(1), status: "completo", terminal: true };
    expect(mergeJobProgress(done, run(0.3))).toBe(done);
  });
});

describe("useJobProgress", () => {
  it("writes every update into the touched cache entries and sends the bearer token", async () => {
    (globalThis.fetch as any).mockResolvedValue(sse([frame({ progress: 0.4, stage: "estrutura 2 de 5" })], { hang: true }));
    const { result } = renderHook(() => useJobProgress(base), { wrapper });
    await waitFor(() => expect(qc.getQueryData<Job>(READ)?.progress).toBe(40));
    expect(result.current.progress?.stage).toBe("estrutura 2 de 5");
    expect(result.current.mode).toBe("stream");
    const [, init] = (globalThis.fetch as any).mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer jwt");
  });

  it("while the stream is live the read does NOT poll (push replaces the poll)", async () => {
    (globalThis.fetch as any).mockResolvedValue(sse([frame({ progress: 0.1 })], { hang: true }));
    const opts = jobPolling((d: Job | undefined) => d?.status === "processando", 3000);
    const q = { state: { data: qc.getQueryData<Job>(READ) }, queryKey: READ as unknown as readonly unknown[] };
    expect(opts.refetchInterval(q)).toBe(3000);
    renderHook(() => useJobProgress(base), { wrapper });
    await waitFor(() => expect(opts.refetchInterval(q)).toBe(false));
  });

  it("closes on the terminal frame and refreshes the authoritative read", async () => {
    (globalThis.fetch as any).mockResolvedValue(
      sse([frame({ progress: 0.5 }), frame({ status: "completo", progress: 1, terminal: true })]),
    );
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useJobProgress(base), { wrapper });
    await waitFor(() => expect(result.current.mode).toBe("done"));
    expect(result.current.progress?.status).toBe("completo");
    expect(spy).toHaveBeenCalledWith({ queryKey: READ });
    expect((globalThis.fetch as any).mock.calls.length).toBe(1); // no reconnect after terminal
  });

  it("falls back to the polling hand-off when the stream is refused", async () => {
    vi.useFakeTimers();
    (globalThis.fetch as any).mockResolvedValue(sse([], { ok: false, status: 401 }));
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useJobProgress({ ...base, fallbackAfterMs: 2000 }), { wrapper });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(result.current.mode).toBe("polling");
    expect(spy).toHaveBeenCalledWith({ queryKey: READ }); // handOffToPolling invalidates the read
    const opts = jobPolling((d: Job | undefined) => d?.status === "processando", 3000);
    const q = { state: { data: qc.getQueryData<Job>(READ) }, queryKey: READ as unknown as readonly unknown[] };
    expect(opts.refetchInterval(q)).toBe(3000); // the poll is back
  });

  it("is idle (no connection) without a job id", () => {
    const { result } = renderHook(() => useJobProgress({ ...base, jobId: null }), { wrapper });
    expect(result.current.mode).toBe("idle");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

/** Polling cadence for non-terminal transcriptions (transcription-contract §4). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";

const get = vi.hoisted(() => vi.fn());
vi.mock("@noctusai/seed/infra", () => ({ api: { get, put: vi.fn(), post: vi.fn() } }));
vi.mock("@/hooks/useCardHub", () => ({ uploadMultipart: vi.fn() }));

import { useCerebroPerguntas } from "./useCerebroPerguntas";

const brain = (status: string) => ({
  data: {
    id: "b1", synthesis_status: "idle",
    answers: [{ question_id: "q1", text: "", review: { status: "none" }, transcricao: { id: "t", status, posicao: 1 } }],
  },
});
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);
async function tick(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  get.mockReset();
});

describe("useCerebroPerguntas polling", () => {
  it("3 s for 30 s, then 10 s, stops on terminal", async () => {
    get.mockResolvedValue(brain("processando"));
    renderHook(() => useCerebroPerguntas("b1"), { wrapper });
    await tick(0);
    expect(get).toHaveBeenCalledTimes(1);
    await tick(3000);
    expect(get).toHaveBeenCalledTimes(2);
    await tick(27_000); // → 30 s : 9 more fast polls
    const aos30 = get.mock.calls.length;
    expect(aos30).toBeGreaterThanOrEqual(10);
    await tick(10_000);
    expect(get.mock.calls.length - aos30).toBeLessThanOrEqual(2); // slow cadence
    get.mockResolvedValue(brain("concluida"));
    await tick(10_000);
    const parou = get.mock.calls.length;
    await tick(60_000);
    expect(get.mock.calls.length).toBe(parou);
  });
});

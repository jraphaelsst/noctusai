/**
 * F87 — after "Solicitar emissão" the first re-reads may show no cell in
 * flight yet (the async job has not created the consulta rows). The grid must
 * keep polling through that window (seed `handOffToPolling`), follow the cell
 * while it runs, and stop once it settled.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import React from "react";
import { resetJobHandOffs } from "@noctusai/lib";

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get, post } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));

import { POLL_MS, useCertidoesPartes, useSolicitarEmissao } from "./useCertidoesPartes";

const grid = (status: string | null) => ({
  partes: status ? [{ celulas: { a: { status_processamento: status, aguarda_humano: false } } }] : [],
});

describe("Solicitar emissão hands the grid off to polling (F87)", () => {
  let qc: QueryClient;
  beforeEach(() => {
    vi.useFakeTimers();
    resetJobHandOffs();
    qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
    qc.mount();
    get.mockReset();
    post.mockReset();
  });
  afterEach(() => {
    qc.unmount();
    qc.clear();
    resetJobHandOffs();
    vi.useRealTimers();
  });

  it("keeps polling while the job has not shown up, then stops once the cell settled", async () => {
    const answers = [grid(null), grid(null), grid(null), grid("processando"), grid("sucesso")];
    let n = 0;
    get.mockImplementation(async () => answers[Math.min(n++, answers.length - 1)]);
    post.mockResolvedValue({ consulta_id: "k1", resultados: [] });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);
    const { result } = renderHook(
      () => ({ read: useCertidoesPartes("c1"), emitir: useSolicitarEmissao("c1") }),
      { wrapper },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(get).toHaveBeenCalledTimes(1); // idle grid: no polling on its own

    await act(async () => {
      result.current.emitir.mutate({ kind: "pessoa", alvoId: "p1", tipos: null } as never);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(get).toHaveBeenCalledTimes(2); // the hand-off re-read — still empty (the race)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS * 3);
    });
    expect(get).toHaveBeenCalledTimes(5); // polled through the race, saw it run, saw it settle
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS * 5);
    });
    expect(get).toHaveBeenCalledTimes(5); // settled ⇒ the poll is over
  });
});

/**
 * useExtracaoPollingInvalidation — Bug 2 (prod card 755253934).
 *
 * Extraction runs server-side and asynchronously: the upload response (and
 * the immediate invalidation `useDocumentoMutations().upload.onSuccess`
 * fires) lands BEFORE the OCR job has even started, so the first refetch it
 * triggers still reads the pre-extraction record. Nothing invalidates
 * "Qualificação para contrato" / a party's "Dados obrigatórios" / negociação
 * again once the job actually finishes — until this hook's poll notices the
 * transition.
 *
 * A REAL `QueryClient` (not the module-level `@tanstack/react-query` mock
 * every other `useCardHub` suite uses) is deliberate here: the bug is about
 * cache INVALIDATION TIMING across TWO fetches of the SAME query key, which
 * a mocked `useQuery`/`useQueryClient` (a single static return value, no
 * re-render on data change) cannot exercise. `qc.refetchQueries(...)`
 * substitutes for the timer-driven `refetchInterval` firing — it exercises
 * the same transition-detection effect the interval would trigger, without
 * coupling this test to the interval's exact millisecond value.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "tok123" } } }),
    },
  },
}));

import { useExtracaoPollingInvalidation } from "./useCardHub";

const DOCUMENTOS_KEY = (id: string) => ["sw", "cardHub", id, "documentos"];

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useExtracaoPollingInvalidation", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
  });

  afterEach(() => {
    qc.clear();
  });

  it("🔴 invalidates qualificação, checklist, card, partes and the clientes family the FIRST time a pending document turns terminal — the exact gap 9ce161f82 left open (it invalidated QUALIFICACAO_ROOT_KEY from useDadosPessoaisMutation/useDecidirConflitoMutation, both client-initiated writes, never from a server-only extraction finishing)", async () => {
    mockGet
      .mockResolvedValueOnce({ items: [{ id: "d1", extracao_status: "pendente" }] })
      .mockResolvedValueOnce({ items: [{ id: "d1", extracao_status: "ok" }] });

    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useExtracaoPollingInvalidation("cli-1"), {
      wrapper: makeWrapper(qc),
    });

    // Waits for the "pendente" data to actually LAND (not just for the fetch
    // to have been CALLED) — otherwise a fast-resolving mock can settle the
    // first fetch and the manually-triggered second one in the same tick,
    // and the component only ever renders the FINAL ("ok") data, skipping
    // the "pendente" render this test needs to establish the transition's
    // "before" state.
    await waitFor(() =>
      expect(qc.getQueryData(DOCUMENTOS_KEY("cli-1"))).toEqual([
        { id: "d1", extracao_status: "pendente" },
      ]),
    );
    expect(invalidateSpy).not.toHaveBeenCalled();

    // Simulates the refetch `refetchInterval` would have fired.
    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("cli-1") });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["sw", "cardHub", "qualificacao"] }),
      );
    });
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["sw", "cardHub", "cli-1", "documento-checklist"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["sw", "cardHub", "cli-1", "card"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["sw", "cardHub", "cli-1", "compradores", "comprador"] }),
    );
    // The broad prefix — reaches `useNegociacao`'s
    // `["sw","clientes",id,"negociacao"]` key without this file importing it.
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["sw", "clientes"] }),
    );
  });

  it("does NOT invalidate anything while a document is STILL pending — no transition has happened yet", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: "pendente" }] });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useExtracaoPollingInvalidation("cli-1"), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("cli-1") });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("a document with no pending extraction (null — a type deve_extrair never reads) never invalidates on a later refetch", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: null }] });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useExtracaoPollingInvalidation("cli-1"), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("cli-1") });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

/**
 * useFinanciamentoExtracaoPollingInvalidation — P1/883 (2026-09-25),
 * negociação/financiamento extraction contract (§E.5/§F).
 *
 * `useFinanciamento` already polls (and re-renders on) a document's OWN
 * `extracao_status`, but nothing invalidated the surfaces a landed reading
 * ALSO fills — negociação (H2/H4), favorecidos (H5) and agentes financeiros
 * (H7). Same test technique as
 * `useEmpresas.extracaoPolling.test.tsx`/`useImovelDados`'s own sibling: a
 * REAL `QueryClient`, because the bug is cache invalidation TIMING across
 * two fetches of the SAME query key, which a mocked `useQuery` cannot
 * exercise.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));

import { useFinanciamentoExtracaoPollingInvalidation } from "./useFinanciamento";

const FINANCIAMENTO_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "financiamento"];
const NEGOCIACAO_KEY = (clienteId: string) => ["sw", "clientes", clienteId, "negociacao"];
const ESTRUTURADA_KEY = (clienteId: string) => [
  "sw",
  "clientes",
  clienteId,
  "negociacao",
  "estruturada",
];
const CONFLITOS_KEY = (clienteId: string) => [
  "sw",
  "clientes",
  clienteId,
  "negociacao",
  "conflitos",
];
const AGENTES_KEY = ["sw", "agentes-financeiros"];

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function financiamentoComDocs(docs: Array<{ id: string; extracao_status: string | null }>) {
  return { documentos: docs };
}

describe("useFinanciamentoExtracaoPollingInvalidation", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
  });

  afterEach(() => {
    qc.clear();
  });

  it("🔴 invalidates negociação/estruturada/conflitos/agentes-financeiros the FIRST time a pending document turns terminal", async () => {
    mockGet
      .mockResolvedValueOnce(financiamentoComDocs([{ id: "d1", extracao_status: "pendente" }]))
      .mockResolvedValueOnce(financiamentoComDocs([{ id: "d1", extracao_status: "ok" }]));

    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useFinanciamentoExtracaoPollingInvalidation("cli-1"), {
      wrapper: makeWrapper(qc),
    });

    await waitFor(() =>
      expect(qc.getQueryData(FINANCIAMENTO_KEY("cli-1"))).toEqual(
        financiamentoComDocs([{ id: "d1", extracao_status: "pendente" }]),
      ),
    );
    expect(invalidateSpy).not.toHaveBeenCalled();

    // Simulates the refetch `refetchInterval` would have fired.
    await qc.refetchQueries({ queryKey: FINANCIAMENTO_KEY("cli-1") });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: NEGOCIACAO_KEY("cli-1") }),
      );
    });
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: FINANCIAMENTO_KEY("cli-1") }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ESTRUTURADA_KEY("cli-1") }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: CONFLITOS_KEY("cli-1") }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: AGENTES_KEY }),
    );
  });

  it("does NOT invalidate anything while a document is STILL pending — no transition has happened yet", async () => {
    mockGet.mockResolvedValue(financiamentoComDocs([{ id: "d1", extracao_status: "processando" }]));
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useFinanciamentoExtracaoPollingInvalidation("cli-1"), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    await qc.refetchQueries({ queryKey: FINANCIAMENTO_KEY("cli-1") });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("a document with no pending extraction (null — no registered extractor) never invalidates on a later refetch", async () => {
    mockGet.mockResolvedValue(financiamentoComDocs([{ id: "d1", extracao_status: null }]));
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useFinanciamentoExtracaoPollingInvalidation("cli-1"), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    await qc.refetchQueries({ queryKey: FINANCIAMENTO_KEY("cli-1") });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("a null clienteId never fetches or invalidates", async () => {
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useFinanciamentoExtracaoPollingInvalidation(null), {
      wrapper: makeWrapper(qc),
    });

    expect(mockGet).not.toHaveBeenCalled();
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

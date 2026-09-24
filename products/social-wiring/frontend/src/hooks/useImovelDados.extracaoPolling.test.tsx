/**
 * useImovelExtracaoPollingInvalidation — P1 folder 883 (2026-09-24).
 *
 * `useImovelDocumentos` already polled a document's OWN `extracao_status`/
 * `extracao_matricula` (so `ImovelDocumentosCard`'s "Lendo…" spinner did
 * update), but nothing ever invalidated `useImovelDados` — the SEPARATE
 * query that holds `numero_matricula`/`prefeitura_cadastro_imobiliario`,
 * filled by the full transcription's D1 apply on its own schedule. "Dados
 * do Imóvel" kept showing the pre-extraction snapshot until a hard reload —
 * the imóvel sibling of the bug `useCardHub.useExtracaoPollingInvalidation`
 * (b9ff02e15) already fixed for a cliente's checklist/qualificação.
 *
 * A REAL `QueryClient`, same reason `useCardHub.extracaoPolling.test.tsx`
 * gives: the bug is cache invalidation TIMING across two fetches of the
 * SAME query key, which a mocked `useQuery` (a static return, no re-render
 * on data change) cannot exercise.
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

import { useImovelExtracaoPollingInvalidation } from "./useImovelDados";

const DOCUMENTOS_KEY = (codigo: string) => ["sw", "imovel-dados", codigo, "documentos"];
const FAMILY_KEY = (codigo: string) => ["sw", "imovel-dados", codigo];
const CONTRATO_FAMILY_KEY = (codigo: string) => ["sw", "imovel-contrato", codigo];

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useImovelExtracaoPollingInvalidation", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
  });

  afterEach(() => {
    qc.clear();
  });

  it("🔴 invalidates the imovel-dados and imovel-contrato families the FIRST time a pending document turns terminal", async () => {
    mockGet
      .mockResolvedValueOnce({ items: [{ id: "d1", extracao_status: "pendente" }] })
      .mockResolvedValueOnce({ items: [{ id: "d1", extracao_status: "ok" }] });

    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useImovelExtracaoPollingInvalidation("ONE7515"), {
      wrapper: makeWrapper(qc),
    });

    // Waits for the "pendente" data to actually LAND — see the useCardHub
    // sibling test's own comment for why this matters.
    await waitFor(() =>
      expect(qc.getQueryData(DOCUMENTOS_KEY("ONE7515"))).toEqual([
        { id: "d1", extracao_status: "pendente" },
      ]),
    );
    expect(invalidateSpy).not.toHaveBeenCalled();

    // Simulates the refetch `refetchInterval` would have fired.
    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("ONE7515") });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: FAMILY_KEY("ONE7515") }),
      );
    });
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: CONTRATO_FAMILY_KEY("ONE7515") }),
    );
  });

  it("does NOT invalidate anything while a document is STILL pending — no transition has happened yet", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: "processando" }] });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useImovelExtracaoPollingInvalidation("ONE7515"), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("ONE7515") });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("a document with no pending extraction (null) never invalidates on a later refetch", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: null }] });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useImovelExtracaoPollingInvalidation("ONE7515"), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("ONE7515") });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("a null codigo never fetches or invalidates", async () => {
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useImovelExtracaoPollingInvalidation(null), {
      wrapper: makeWrapper(qc),
    });

    expect(mockGet).not.toHaveBeenCalled();
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

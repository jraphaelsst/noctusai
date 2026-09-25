/**
 * useEmpresaExtracaoPollingInvalidation — P1/883 (2026-09-25).
 *
 * `useEmpresaDocumentos` already polled a Cartão CNPJ document's OWN
 * `extracao_status` (so `EmpresaCartaoSlot`'s "Lendo…" state updated), but
 * nothing ever invalidated `useEmpresasDoCard` — the SEPARATE query that
 * carries the E1 verdict (`situacao_cadastral`/`motivo`/`exige_certidoes`)
 * `dados_service.aplicar_cartao`'s group-level D1 apply fills on landing.
 * `EmpresasSection`'s badge kept showing the pre-extraction verdict until a
 * hard reload — the empresas sibling of the bug `useImovelDados.
 * useImovelExtracaoPollingInvalidation` fixed for imóvel docs (this file
 * mirrors that one's own test technique).
 *
 * A REAL `QueryClient`, same reason both siblings give: the bug is cache
 * invalidation TIMING across two fetches of the SAME query key, which a
 * mocked `useQuery` (a static return, no re-render on data change) cannot
 * exercise.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import { useEmpresaExtracaoPollingInvalidation } from "./useEmpresas";

const DOCUMENTOS_KEY = (empresaId: string) => ["sw", "empresas", empresaId, "documentos"];
const EMPRESAS_DO_CARD_KEY = (clienteId: string) => ["sw", "clientes", clienteId, "empresas"];
const CHECKLIST_KEY = (empresaId: string) => ["sw", "empresas", empresaId, "checklist"];

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useEmpresaExtracaoPollingInvalidation", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
  });

  afterEach(() => {
    qc.clear();
  });

  it("🔴 invalidates the card's empresas list + this empresa's own family the FIRST time a pending document turns terminal", async () => {
    mockGet
      .mockResolvedValueOnce({ items: [{ id: "d1", extracao_status: "pendente" }] })
      .mockResolvedValueOnce({ items: [{ id: "d1", extracao_status: "ok" }] });

    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useEmpresaExtracaoPollingInvalidation("emp-1", "cli-1"), {
      wrapper: makeWrapper(qc),
    });

    // Waits for the "pendente" data to actually LAND — see the imóvel
    // sibling test's own comment for why this matters.
    await waitFor(() =>
      expect(qc.getQueryData(DOCUMENTOS_KEY("emp-1"))).toEqual({
        items: [{ id: "d1", extracao_status: "pendente" }],
      }),
    );
    expect(invalidateSpy).not.toHaveBeenCalled();

    // Simulates the refetch `refetchInterval` would have fired.
    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("emp-1") });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: EMPRESAS_DO_CARD_KEY("cli-1") }),
      );
    });
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: DOCUMENTOS_KEY("emp-1") }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: CHECKLIST_KEY("emp-1") }),
    );
  });

  it("does NOT invalidate anything while a document is STILL pending — no transition has happened yet", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: "processando" }] });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useEmpresaExtracaoPollingInvalidation("emp-1", "cli-1"), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("emp-1") });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("a document with no pending extraction (null) never invalidates on a later refetch", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: null }] });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useEmpresaExtracaoPollingInvalidation("emp-1", "cli-1"), {
      wrapper: makeWrapper(qc),
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    await qc.refetchQueries({ queryKey: DOCUMENTOS_KEY("emp-1") });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("a null empresaId never fetches or invalidates", async () => {
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useEmpresaExtracaoPollingInvalidation(null, "cli-1"), {
      wrapper: makeWrapper(qc),
    });

    expect(mockGet).not.toHaveBeenCalled();
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

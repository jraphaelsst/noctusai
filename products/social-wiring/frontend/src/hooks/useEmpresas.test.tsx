/**
 * `useEmpresas` — the P0c contract's card-hub-family hooks
 * (`project-history/roadmaps/sw-drive-extraction-P0c-contract.md` §D.1-4).
 *
 * Focuses on the two behaviours the contract calls out explicitly:
 * `useEmpresasDoCard`'s basic bare-payload read, and `useEmpresaDocumentos`'s
 * polling contract — mirrors `useCardHub.extracaoPolling.test.tsx`'s own
 * "call the registered `refetchInterval` directly off a real `QueryClient`"
 * technique, which is deterministic (no fake timers, no real 2.5s wait).
 */
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider, type Query } from "@tanstack/react-query";
import { renderHook, waitFor, act } from "@testing-library/react";

const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: vi.fn(), put: vi.fn(), delete: mockDelete },
}));

import {
  empresaExtracaoEmAndamento,
  useEmpresaDocumentoUrl,
  useEmpresaDocumentos,
  useEmpresasDoCard,
  useRemoverEmpresaDocumento,
} from "./useEmpresas";

const DOCUMENTOS_KEY = (empresaId: string) => ["sw", "empresas", empresaId, "documentos"];
const EMPRESAS_DO_CARD_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "empresas"];

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("empresaExtracaoEmAndamento", () => {
  it("is true only for the two in-flight statuses — false for every terminal one, including null", () => {
    expect(empresaExtracaoEmAndamento("pendente")).toBe(true);
    expect(empresaExtracaoEmAndamento("processando")).toBe(true);
    expect(empresaExtracaoEmAndamento("ok")).toBe(false);
    expect(empresaExtracaoEmAndamento("sem_dados")).toBe(false);
    expect(empresaExtracaoEmAndamento("erro")).toBe(false);
    expect(empresaExtracaoEmAndamento(null)).toBe(false);
  });
});

describe("useEmpresasDoCard", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
    mockPost.mockReset();
  });

  afterEach(() => qc.clear());

  it("reads the bare `{atendimento_id, referencia, items}` envelope — a card route, not the certidões `success_response()` wrapper", async () => {
    const payload = {
      atendimento_id: "at-1",
      referencia: "2026-09-24",
      items: [],
    };
    mockGet.mockResolvedValue(payload);

    const { result } = renderHook(() => useEmpresasDoCard("cli-1"), {
      wrapper: makeWrapper(qc),
    });

    await waitFor(() => expect(result.current.data).toEqual(payload));
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/cli-1/empresas");
  });

  it("does not fetch when clienteId is null", () => {
    renderHook(() => useEmpresasDoCard(null), { wrapper: makeWrapper(qc) });
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("query key matches the contract's `[\"sw\",\"clientes\",id,\"empresas\"]`", async () => {
    mockGet.mockResolvedValue({ atendimento_id: null, referencia: "2026-09-24", items: [] });
    renderHook(() => useEmpresasDoCard("cli-1"), { wrapper: makeWrapper(qc) });
    await waitFor(() =>
      expect(qc.getQueryData(EMPRESAS_DO_CARD_KEY("cli-1"))).toBeTruthy(),
    );
  });
});

describe("useEmpresaDocumentos — polling", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
  });

  afterEach(() => qc.clear());

  function refetchIntervalOf(empresaId: string) {
    const query = qc.getQueryCache().find({ queryKey: DOCUMENTOS_KEY(empresaId) }) as Query;
    const options = query.options as { refetchInterval?: (q: Query) => number | false };
    return options.refetchInterval!(query);
  }

  it("keeps polling while a document is pendente", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: "pendente" }] });
    renderHook(() => useEmpresaDocumentos("emp-1"), { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    expect(refetchIntervalOf("emp-1")).toBe(2500);
  });

  it("keeps polling while a document is processando", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: "processando" }] });
    renderHook(() => useEmpresaDocumentos("emp-2"), { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    expect(refetchIntervalOf("emp-2")).toBe(2500);
  });

  it("🔴 stops polling the instant every document reaches a terminal state (ok)", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: "ok" }] });
    renderHook(() => useEmpresaDocumentos("emp-3"), { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    expect(refetchIntervalOf("emp-3")).toBe(false);
  });

  it("never polls a card whose only document never reads (extracao_status null)", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", extracao_status: null }] });
    renderHook(() => useEmpresaDocumentos("emp-4"), { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1));

    expect(refetchIntervalOf("emp-4")).toBe(false);
  });

  it("does not fetch when empresaId is null", () => {
    renderHook(() => useEmpresaDocumentos(null), { wrapper: makeWrapper(qc) });
    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe("useEmpresaDocumentoUrl", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
  });

  afterEach(() => qc.clear());

  it("§D.4 — mints ONE URL, no `intent` param (unlike the person-scoped documentos)", async () => {
    mockGet.mockResolvedValue({ url: "https://signed.example/x", expires_at: "2026-09-24T01:00:00Z" });
    const { result } = renderHook(() => useEmpresaDocumentoUrl("emp-1"), {
      wrapper: makeWrapper(qc),
    });

    await act(async () => {
      result.current.mutate("doc-1");
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/empresas/emp-1/documentos/doc-1/url");
    expect(result.current.data).toEqual({
      url: "https://signed.example/x",
      expires_at: "2026-09-24T01:00:00Z",
    });
  });
});

describe("useRemoverEmpresaDocumento", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockDelete.mockReset();
  });

  afterEach(() => qc.clear());

  it("§D.4 — sends `motivo` as a query param, never a JSON body", async () => {
    mockDelete.mockResolvedValue(undefined);
    const { result } = renderHook(() => useRemoverEmpresaDocumento("emp-1", "cli-1"), {
      wrapper: makeWrapper(qc),
    });

    await act(async () => {
      result.current.mutate({ documentoId: "doc-1", motivo: "Documento errado" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockDelete).toHaveBeenCalledWith(
      "/api/empresas/emp-1/documentos/doc-1?motivo=Documento%20errado",
    );
  });

  it("invalidates the empresa's documentos AND the card's empresas list", async () => {
    mockDelete.mockResolvedValue(undefined);
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useRemoverEmpresaDocumento("emp-1", "cli-1"), {
      wrapper: makeWrapper(qc),
    });

    await act(async () => {
      result.current.mutate({ documentoId: "doc-1", motivo: "x" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["sw", "empresas", "emp-1", "documentos"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["sw", "clientes", "cli-1", "empresas"] }),
    );
  });

  it("skips the card-empresas invalidation when no clienteId was given", async () => {
    mockDelete.mockResolvedValue(undefined);
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useRemoverEmpresaDocumento("emp-1"), {
      wrapper: makeWrapper(qc),
    });

    await act(async () => {
      result.current.mutate({ documentoId: "doc-1", motivo: "x" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["sw", "empresas", "emp-1", "documentos"] }),
    );
  });
});

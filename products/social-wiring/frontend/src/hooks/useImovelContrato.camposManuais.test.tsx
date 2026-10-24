/**
 * Migration 306 — the typed-by-hand writes (owner directive 2026-10-24: no
 * field is upload-only). A REAL `QueryClient`: what these pin is that the
 * server's answer lands in the cache the screen reads (cache-write, never
 * invalidate-only), which a mocked `useQuery` cannot show.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { mockGet, mockPut, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPut: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: mockPut, delete: mockDelete },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import {
  useConfirmarDescricaoImovel,
  useConfirmarUltimaTransferenciaManual,
  useRemoverCertidaoManual,
  useSalvarCertidaoManual,
  type ImovelCertidao,
} from "./useImovelContrato";

const CODIGO = "AP1234";
const CERTIDOES_KEY = ["sw", "imovel-contrato", CODIGO, "certidoes"];
const DESCRICAO_KEY = ["sw", "imovel-contrato", CODIGO, "descricao-imovel"];

let qc: QueryClient;
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function manual(over: Partial<ImovelCertidao> = {}): ImovelCertidao {
  return {
    tipo: "cnd_condominio",
    documento_id: null,
    numero: null,
    emitida_em: "2026-10-01",
    validade_ate: null,
    resultado: "negativa",
    inscricao_imobiliaria: null,
    confirmado: true,
    sem_arquivo: true,
    manual_id: "m-1",
    ...over,
  };
}

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  // Settle's background refetch has no queryFn registered here — keep it inert.
  mockGet.mockResolvedValue({ items: [], total: 0 });
});
afterEach(() => {
  vi.clearAllMocks();
  qc.clear();
});

describe("useSalvarCertidaoManual", () => {
  it("PUTs the typed record and commits the server's certidões into the cache", async () => {
    mockPut.mockResolvedValue({ items: [manual()], total: 1, manuais: {} });
    qc.setQueryData(CERTIDOES_KEY, []);
    const { result } = renderHook(() => useSalvarCertidaoManual(CODIGO), { wrapper });

    await act(async () => {
      result.current.mutate({
        tipo: "cnd_condominio",
        valores: { emitida_em: "2026-10-01", resultado: "negativa" },
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPut).toHaveBeenCalledWith(
      "/api/imoveis/AP1234/certidoes/cnd_condominio/manual",
      { emitida_em: "2026-10-01", resultado: "negativa" },
    );
    expect(qc.getQueryData(CERTIDOES_KEY)).toEqual([manual()]);
  });
});

describe("useRemoverCertidaoManual", () => {
  it("drops the typed reading optimistically and commits what the server answers", async () => {
    let resolver: (v: unknown) => void = () => {};
    mockDelete.mockReturnValue(new Promise((r) => (resolver = r)));
    qc.setQueryData(CERTIDOES_KEY, [manual()]);
    const { result } = renderHook(() => useRemoverCertidaoManual(CODIGO), { wrapper });

    act(() => result.current.mutate({ tipo: "cnd_condominio" }));
    await waitFor(() => expect(qc.getQueryData(CERTIDOES_KEY)).toEqual([]));
    expect(mockDelete).toHaveBeenCalledWith("/api/imoveis/AP1234/certidoes/cnd_condominio/manual");

    const doc = manual({ documento_id: "doc-1", sem_arquivo: false, manual_id: null });
    await act(async () => resolver({ items: [doc], total: 1, manuais: {} }));
    await waitFor(() => expect(qc.getQueryData(CERTIDOES_KEY)).toEqual([doc]));
  });

  it("rolls the optimistic removal back on failure", async () => {
    mockDelete.mockRejectedValue(new Error("[404] não encontrado"));
    qc.setQueryData(CERTIDOES_KEY, [manual()]);
    const { result } = renderHook(() => useRemoverCertidaoManual(CODIGO), { wrapper });
    await act(async () => result.current.mutate({ tipo: "cnd_condominio" }));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData(CERTIDOES_KEY)).toEqual([manual()]);
  });
});

describe("useConfirmarDescricaoImovel", () => {
  it("PUTs the typed text and commits the response", async () => {
    const resposta = {
      codigo: CODIGO,
      derivado: null,
      confirmado: { texto: "Casa ficticia", confirmado_por: null, confirmado_em: null },
      efetivo: "Casa ficticia",
      origem: "manual",
    };
    mockPut.mockResolvedValue({ data: resposta });
    mockGet.mockResolvedValue({ data: resposta });
    const { result } = renderHook(() => useConfirmarDescricaoImovel(CODIGO), { wrapper });
    await act(async () => result.current.mutate("Casa ficticia"));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPut).toHaveBeenCalledWith("/api/matriculas/imoveis/AP1234/descricao-imovel", {
      texto: "Casa ficticia",
    });
    expect(qc.getQueryData(DESCRICAO_KEY)).toEqual(resposta);
  });
});

describe("useConfirmarUltimaTransferenciaManual", () => {
  it("sends the typed sellers (and [] when none, a full replace)", async () => {
    mockPut.mockResolvedValue({ data: {} });
    const { result } = renderHook(() => useConfirmarUltimaTransferenciaManual(CODIGO), { wrapper });
    await act(async () =>
      result.current.mutate({
        data: null,
        natureza: null,
        semRegistro: false,
        transmitentes: ["Fulano Ficticio"],
      }),
    );
    expect(mockPut).toHaveBeenLastCalledWith("/api/matriculas/imoveis/AP1234/ultima-transferencia", {
      data: null,
      natureza: null,
      sem_registro: false,
      transmitentes: ["Fulano Ficticio"],
    });
    await act(async () =>
      result.current.mutate({ data: "2023-01-01", natureza: null, semRegistro: false }),
    );
    expect(mockPut).toHaveBeenLastCalledWith("/api/matriculas/imoveis/AP1234/ultima-transferencia", {
      data: "2023-01-01",
      natureza: null,
      sem_registro: false,
      transmitentes: [],
    });
  });
});

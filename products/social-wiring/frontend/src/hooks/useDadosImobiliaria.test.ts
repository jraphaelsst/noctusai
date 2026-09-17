/**
 * Tests for useDadosImobiliaria / useSalvarDadosImobiliaria — the migration
 * 117 (contract F6) fields joined this slice:
 * `plataforma_assinatura_nome`, `plataforma_assinatura_url`,
 * `posse_multa_diaria`, `prazo_pendencias_padrao_dias`.
 *
 * What matters here:
 *   1. GET hits the right endpoint and the response's new fields survive
 *      the round trip untouched (no client-side coercion hiding a
 *      backend-shape drift).
 *   2. `showSkeleton` / `isRefreshing` are derived off `isPending` /
 *      `isFetching` / `data`, never a bare `isLoading` — see
 *      `KB § PATTERNS/frontend/lying-loading-state.md`.
 *   3. PUT sends the caller's payload verbatim and the mutation seeds the
 *      cache with the server's response (no refetch window).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockPut, setQueryDataMock, useQueryMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPut: vi.fn(),
  setQueryDataMock: vi.fn(),
  useQueryMock: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, put: mockPut },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = useQueryMock;
  const useMutation = vi.fn(
    ({
      mutationFn,
      onSuccess,
    }: {
      mutationFn: (v: unknown) => unknown;
      onSuccess?: (r: unknown, v: unknown) => void;
    }) => ({
      mutate: (
        vars: unknown,
        opts?: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void },
      ) => {
        Promise.resolve(mutationFn(vars))
          .then((result) => {
            onSuccess?.(result, vars);
            opts?.onSuccess?.(result);
          })
          .catch((err) => opts?.onError?.(err));
      },
      isPending: false,
      _mutationFn: mutationFn,
    }),
  );
  const useQueryClient = vi.fn(() => ({ setQueryData: setQueryDataMock }));
  return { useQuery, useMutation, useQueryClient };
});

import { useDadosImobiliaria, useSalvarDadosImobiliaria } from "./useDadosImobiliaria";

function queryState(over: Record<string, unknown> = {}) {
  useQueryMock.mockImplementation(({ queryFn }: { queryFn: () => unknown }) => ({
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    _queryFn: queryFn,
    ...over,
  }));
}

beforeEach(() => {
  vi.clearAllMocks();
  queryState();
});

const FIXTURE = {
  razao_social: "Imobiliária Exemplo LTDA",
  nome_fantasia: null,
  cnpj: null,
  creci_pj: null,
  responsavel_nome: null,
  responsavel_creci: null,
  telefone: null,
  email: null,
  endereco_cep: null,
  endereco_logradouro: null,
  endereco_numero: null,
  endereco_complemento: null,
  endereco_bairro: null,
  endereco_cidade: null,
  endereco_uf: null,
  plataforma_assinatura_nome: "ClickSign",
  plataforma_assinatura_url: "https://app.clicksign.com",
  posse_multa_diaria: 150.5,
  prazo_pendencias_padrao_dias: 10,
  updated_at: "2026-09-17T00:00:00Z",
};

describe("useDadosImobiliaria", () => {
  it("GETs /api/settings/imobiliaria", async () => {
    mockGet.mockResolvedValue(FIXTURE);
    const hook = useDadosImobiliaria() as any;

    const result = await hook._queryFn();

    expect(mockGet).toHaveBeenCalledWith("/api/settings/imobiliaria");
    expect(result).toEqual(FIXTURE);
  });

  it("round-trips the migration 117 fields untouched", async () => {
    mockGet.mockResolvedValue(FIXTURE);
    const hook = useDadosImobiliaria() as any;
    const result = await hook._queryFn();

    expect(result.plataforma_assinatura_nome).toBe("ClickSign");
    expect(result.plataforma_assinatura_url).toBe("https://app.clicksign.com");
    expect(result.posse_multa_diaria).toBe(150.5);
    expect(result.prazo_pendencias_padrao_dias).toBe(10);
  });

  it("showSkeleton is true only on the first load (nothing to show yet)", () => {
    queryState({ isPending: true, isFetching: true, data: undefined });
    expect(useDadosImobiliaria().showSkeleton).toBe(true);
  });

  it("showSkeleton is false once data exists, even mid-refetch", () => {
    queryState({ isPending: false, isFetching: true, data: FIXTURE });
    const hook = useDadosImobiliaria();
    expect(hook.showSkeleton).toBe(false);
    expect(hook.isRefreshing).toBe(true);
  });

  it("isRefreshing is false when nothing is in flight", () => {
    queryState({ isPending: false, isFetching: false, data: FIXTURE });
    const hook = useDadosImobiliaria();
    expect(hook.isRefreshing).toBe(false);
    expect(hook.showSkeleton).toBe(false);
  });
});

describe("useSalvarDadosImobiliaria", () => {
  it("PUTs the payload and seeds the cache with the server's response", async () => {
    mockPut.mockResolvedValue(FIXTURE);
    const hook = useSalvarDadosImobiliaria() as any;

    const payload = {
      plataforma_assinatura_nome: "D4Sign",
      posse_multa_diaria: 200,
      prazo_pendencias_padrao_dias: 15,
    };
    hook.mutate(payload);
    await Promise.resolve();
    await Promise.resolve();

    expect(mockPut).toHaveBeenCalledWith("/api/settings/imobiliaria", payload);
    expect(setQueryDataMock).toHaveBeenCalledWith(
      ["sw", "settings", "imobiliaria"],
      FIXTURE,
    );
  });
});

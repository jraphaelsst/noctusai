/**
 * Tests for useClientes hooks — PROJECT.md §5 (the FE↔BE contract). Mirrors
 * `usePortalRoi.test.ts`'s mocking pattern (mock `@tanstack/react-query`
 * itself so `_queryFn`/`_mutationFn` can be invoked directly, mock
 * `@noctusai/seed/infra`'s `api`).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, mockPatch, mockDelete, invalidateQueriesMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
  invalidateQueriesMock: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, delete: mockDelete },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(
    ({ queryFn, enabled }: { queryFn: () => unknown; enabled?: boolean }) => ({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
      _queryFn: queryFn,
      _enabled: enabled,
    }),
  );
  const useMutation = vi.fn(
    ({
      mutationFn,
      onSuccess,
    }: {
      mutationFn: (v: unknown) => unknown;
      onSuccess?: (r: unknown, v: unknown) => void;
    }) => ({
      mutateAsync: async (vars: unknown) => {
        const result = await mutationFn(vars);
        onSuccess?.(result, vars);
        return result;
      },
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
  const useQueryClient = vi.fn(() => ({ invalidateQueries: invalidateQueriesMock }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  formatCountOrDash,
  maskCpf,
  outrasNegociacoes,
  useClienteMutations,
  useClientesBoard,
  useNegociacoesDoCliente,
  type NegociacaoDoCliente,
} from "./useClientes";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useClientesBoard", () => {
  it("GETs /api/clientes with no query when filters are absent (server defaults to active-only, D4)", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    const hook = useClientesBoard() as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes");
  });

  it("appends ativo=false only for the inactive tab, never ativo=true for the default tab", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    const hook = useClientesBoard({ ativo: false, page: 2, page_size: 24 }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes?page=2&page_size=24&ativo=false");
  });

  it("appends q and corretor_id when given", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    const hook = useClientesBoard({ q: "maria", corretor_id: "c1" }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes?q=maria&corretor_id=c1");
  });

  it("falls back to an empty page on a bare-null response, never undefined", async () => {
    mockGet.mockResolvedValue(null);
    const hook = useClientesBoard() as any;
    const result = await hook._queryFn();
    expect(result).toEqual({ items: [], total: 0, page: 1, pages: 1 });
  });
});

describe("useClienteMutations", () => {
  it("PATCHes /api/clientes/{id} with { ativo: true } to restore (D4)", async () => {
    mockPatch.mockResolvedValue({ id: "cl1", ativo: true });
    const { update } = useClienteMutations();
    await (update as any).mutateAsync({ id: "cl1", body: { ativo: true } });
    expect(mockPatch).toHaveBeenCalledWith("/api/clientes/cl1", { ativo: true });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ["sw", "clientes"] });
  });

  it("DELETEs /api/clientes/{id} and invalidates BOTH the clientes family AND the funil board", async () => {
    mockDelete.mockResolvedValue({
      deleted: true,
      atendimentos_removidos: 2,
      documentos_removidos: 1,
      storage_falhas: [],
    });
    const { remove } = useClienteMutations();
    const result = await (remove as any).mutateAsync("cl1");
    expect(mockDelete).toHaveBeenCalledWith("/api/clientes/cl1");
    expect(result).toEqual({
      deleted: true,
      atendimentos_removidos: 2,
      documentos_removidos: 1,
      storage_falhas: [],
    });
    // The deleted cliente's atendimentos are gone server-side too — the
    // funil board must refetch alongside the clientes family, or it keeps
    // showing a ghost card.
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ["sw", "clientes"] });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ["sw-funil"] });
  });
});

describe("formatCountOrDash", () => {
  it("renders null/undefined as a dash, never a lying zero", () => {
    expect(formatCountOrDash(null)).toBe("—");
    expect(formatCountOrDash(undefined)).toBe("—");
  });

  it("renders a real zero as 0, not a dash", () => {
    expect(formatCountOrDash(0)).toBe("0");
  });

  it("renders pt-BR thousands separators", () => {
    expect(formatCountOrDash(14483)).toBe("14.483");
  });
});

describe("maskCpf", () => {
  it("masks every digit except the last two of the third group plus the check digits (owner's own example)", () => {
    expect(maskCpf("12345678901")).toBe("***.***.*89-01");
  });

  it("masks a punctuated CPF the same way", () => {
    expect(maskCpf("123.456.789-01")).toBe("***.***.*89-01");
  });

  it("renders null/undefined as a dash", () => {
    expect(maskCpf(null)).toBe("—");
    expect(maskCpf(undefined)).toBe("—");
  });

  it("returns an unexpected shape unmasked rather than mangling it", () => {
    expect(maskCpf("123")).toBe("123");
  });

  it("masks a CPF stored with stray spacing identically (digits come through the identifier seam)", () => {
    expect(maskCpf(" 412 954 238 98 ")).toBe("***.***.*38-98");
    expect(maskCpf("412.954.238-98")).toBe("***.***.*38-98");
    expect(maskCpf("41295423898")).toBe("***.***.*38-98");
  });
});

describe("useNegociacoesDoCliente", () => {
  it("GETs /api/clientes/{id}/negociacoes", async () => {
    mockGet.mockResolvedValue({
      cliente_id: "cl1",
      negociacoes: [],
      total_negociacoes: 0,
      candidatos_pendentes: [],
    });
    const hook = useNegociacoesDoCliente("cl1") as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/cl1/negociacoes");
  });

  it("is disabled without a clienteId, never fetching /undefined/negociacoes", () => {
    const hook = useNegociacoesDoCliente(null) as any;
    expect(hook._enabled).toBe(false);
  });
});

describe("outrasNegociacoes", () => {
  const negs: NegociacaoDoCliente[] = [
    {
      atendimento_id: "a1",
      titulo: "Apto Jardins",
      status: null,
      etapa_id: null,
      etapa_label: "Proposta",
      pipeline: null,
      imovel_codigo: "IM-1",
      lado: "comprador",
      papel: "titular",
    },
    {
      atendimento_id: "a2",
      titulo: "Casa Moema",
      status: null,
      etapa_id: null,
      etapa_label: "Visitas",
      pipeline: null,
      imovel_codigo: "IM-2",
      lado: "vendedor",
      papel: "proprietario",
    },
  ];

  it("excludes the given atendimento id", () => {
    expect(outrasNegociacoes(negs, "a1")).toEqual([negs[1]]);
  });

  it("excludes nothing when no id is given", () => {
    expect(outrasNegociacoes(negs, undefined)).toEqual(negs);
    expect(outrasNegociacoes(negs, null)).toEqual(negs);
  });

  it("returns an empty array for undefined input", () => {
    expect(outrasNegociacoes(undefined, "a1")).toEqual([]);
  });
});

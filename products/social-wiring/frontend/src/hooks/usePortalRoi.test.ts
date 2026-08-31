/**
 * Tests for usePortalRoi hooks — PROJECT.md §3 (the FE↔BE contract).
 *
 * Verifies:
 *   · resumo/campanhas/origens build the exact query URLs the contract names.
 *   · Formatters never coerce `null` (never recorded) to a currency/percent
 *     zero — the whole point of §3.5, and the bug §2 fixes one layer down.
 *   · findConflictingCampanha / isConflictError — the client-side 409
 *     resolution the manager dialog relies on.
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

import { ApiError } from "@noctusai/lib";
import { useQuery as mockedUseQuery } from "@tanstack/react-query";
import {
  findConflictingCampanha,
  formatCount,
  formatDateBR,
  formatMoneyOrNaoInformado,
  formatMultipleOrNaoInformado,
  formatPercentOrNaoInformado,
  isConflictError,
  usePortalRoiCampanhas,
  usePortalRoiCampanhaMutations,
  usePortalRoiOrigens,
  usePortalRoiResumo,
  type CampanhaRow,
} from "./usePortalRoi";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("usePortalRoiResumo", () => {
  it("GETs /api/portal-roi/resumo with no query when filters are absent", async () => {
    mockGet.mockResolvedValue({ periodo: null, totais: {}, portais: [] });
    const hook = usePortalRoiResumo() as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/portal-roi/resumo");
  });

  it("appends periodo_inicio/periodo_fim when both are given", async () => {
    mockGet.mockResolvedValue({ periodo: null, totais: {}, portais: [] });
    const hook = usePortalRoiResumo({
      periodo_inicio: "2026-07-01",
      periodo_fim: "2026-07-31",
    }) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith(
      "/api/portal-roi/resumo?periodo_inicio=2026-07-01&periodo_fim=2026-07-31",
    );
  });

  it("falls back to an empty resumo on a bare-null response, never undefined", async () => {
    mockGet.mockResolvedValue(null);
    const hook = usePortalRoiResumo() as any;
    const result = await hook._queryFn();
    expect(result).toEqual({
      periodo: null,
      totais: {
        investimento: null,
        total_leads: 0,
        total_vendas: 0,
        valor_vendas: 0,
        cpl: null,
        roi: null,
        taxa_conversao: null,
      },
      portais: [],
    });
  });

  it("🔴 sets placeholderData so a period change doesn't blank the summary (Cat B regression)", async () => {
    // `filtros.periodo_*` drives the queryKey. Without `placeholderData:
    // (prev) => prev`, changing the period would swap to a fresh key with
    // no cached data and `data` would go `undefined` for one round trip.
    usePortalRoiResumo();
    const call = (mockedUseQuery as any).mock.calls.at(-1)[0];
    expect(typeof call.placeholderData).toBe("function");
    const prev = { periodo: null, totais: {}, portais: [] };
    expect(call.placeholderData(prev)).toBe(prev);
  });
});

describe("usePortalRoiCampanhas", () => {
  it("GETs /api/portal-roi/campanhas?origem_id= and unwraps the envelope", async () => {
    const rows: CampanhaRow[] = [
      {
        id: "c1",
        origem_id: "o1",
        origem_label: "ZAP",
        periodo_inicio: "2026-07-01",
        periodo_fim: "2026-07-31",
        investimento: 3200,
        impressoes: 120000,
        cliques: 4300,
        leads: 812,
        visitas_perfil: null,
        engajamento: null,
        cpc: 0.74,
        cpl: 3.94,
        custo_visita: null,
        observacoes: null,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: null,
      },
    ];
    mockGet.mockResolvedValue({ campanhas: rows });
    const hook = usePortalRoiCampanhas({ origem_id: "o1" }) as any;
    const result = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/portal-roi/campanhas?origem_id=o1");
    expect(result).toEqual(rows);
  });

  it("returns [] when the envelope is bare-null", async () => {
    mockGet.mockResolvedValue(null);
    const hook = usePortalRoiCampanhas({}) as any;
    expect(await hook._queryFn()).toEqual([]);
  });

  it("🔴 sets placeholderData so a filtros change doesn't blank the table (Cat B regression)", async () => {
    usePortalRoiCampanhas({ origem_id: "o1" });
    const call = (mockedUseQuery as any).mock.calls.at(-1)[0];
    expect(typeof call.placeholderData).toBe("function");
    const prev: CampanhaRow[] = [];
    expect(call.placeholderData(prev)).toBe(prev);
  });
});

describe("usePortalRoiOrigens", () => {
  it("GETs /api/portal-roi/origens and unwraps the envelope", async () => {
    mockGet.mockResolvedValue({
      origens: [{ id: "o1", slug: "zap", label: "ZAP", categoria: "portal" }],
    });
    const hook = usePortalRoiOrigens() as any;
    const result = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/portal-roi/origens");
    expect(result).toEqual([{ id: "o1", slug: "zap", label: "ZAP", categoria: "portal" }]);
  });
});

describe("usePortalRoiCampanhaMutations", () => {
  it("POSTs /api/portal-roi/campanhas on create and invalidates the whole family", async () => {
    mockPost.mockResolvedValue({ id: "c1" });
    const { create } = usePortalRoiCampanhaMutations();
    const body = { origem_id: "o1", periodo_inicio: "2026-07-01", periodo_fim: "2026-07-31", investimento: 100 };
    await (create as any).mutateAsync(body);
    expect(mockPost).toHaveBeenCalledWith("/api/portal-roi/campanhas", body);
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ["sw", "portal-roi"] });
  });

  it("PATCHes /api/portal-roi/campanhas/{id} on update", async () => {
    mockPatch.mockResolvedValue({ id: "c1" });
    const { update } = usePortalRoiCampanhaMutations();
    await (update as any).mutateAsync({ id: "c1", body: { investimento: 200 } });
    expect(mockPatch).toHaveBeenCalledWith("/api/portal-roi/campanhas/c1", { investimento: 200 });
  });

  it("DELETEs /api/portal-roi/campanhas/{id} on remove", async () => {
    mockDelete.mockResolvedValue(null);
    const { remove } = usePortalRoiCampanhaMutations();
    await (remove as any).mutateAsync("c1");
    expect(mockDelete).toHaveBeenCalledWith("/api/portal-roi/campanhas/c1");
  });
});

describe("findConflictingCampanha", () => {
  const rows: CampanhaRow[] = [
    {
      id: "c1",
      origem_id: "o1",
      origem_label: "ZAP",
      periodo_inicio: "2026-07-01",
      periodo_fim: "2026-07-31",
      investimento: 3200,
      impressoes: null,
      cliques: null,
      leads: null,
      visitas_perfil: null,
      engajamento: null,
      cpc: null,
      cpl: null,
      custo_visita: null,
      observacoes: null,
      created_at: "",
      updated_at: null,
    },
  ];

  it("finds the row matching the exact (periodo_inicio, periodo_fim) pair", () => {
    const found = findConflictingCampanha(rows, {
      periodo_inicio: "2026-07-01",
      periodo_fim: "2026-07-31",
    });
    expect(found?.id).toBe("c1");
  });

  it("returns null when no period matches", () => {
    expect(
      findConflictingCampanha(rows, { periodo_inicio: "2026-08-01", periodo_fim: "2026-08-31" }),
    ).toBeNull();
  });

  it("excludes the row currently being edited (a save-without-changing-period is not a conflict)", () => {
    expect(
      findConflictingCampanha(
        rows,
        { periodo_inicio: "2026-07-01", periodo_fim: "2026-07-31" },
        "c1",
      ),
    ).toBeNull();
  });
});

describe("isConflictError", () => {
  it("is true for an ApiError with status 409", () => {
    expect(isConflictError(new ApiError(409, "Duplicado"))).toBe(true);
  });

  it("is false for other statuses or non-ApiError values", () => {
    expect(isConflictError(new ApiError(422, "Invalido"))).toBe(false);
    expect(isConflictError(new Error("plain"))).toBe(false);
    expect(isConflictError("nope")).toBe(false);
  });
});

describe("formatters — null is never a lying zero", () => {
  it("formatMoneyOrNaoInformado renders null as an em dash, never R$ 0,00", () => {
    expect(formatMoneyOrNaoInformado(null)).toBe("—");
    expect(formatMoneyOrNaoInformado(undefined)).toBe("—");
  });

  it("formatMoneyOrNaoInformado renders a resolved zero as a real currency zero", () => {
    expect(formatMoneyOrNaoInformado(0)).toBe("R$ 0,00");
  });

  it("formatMoneyOrNaoInformado renders a positive value in pt-BR currency", () => {
    expect(formatMoneyOrNaoInformado(1234.5)).toBe("R$ 1.234,50");
  });

  it("formatPercentOrNaoInformado renders null as an em dash, never 0%", () => {
    expect(formatPercentOrNaoInformado(null)).toBe("—");
  });

  it("formatPercentOrNaoInformado renders a resolved zero as 0,0%, distinct from null", () => {
    expect(formatPercentOrNaoInformado(0)).toBe("0,0%");
  });

  it("formatPercentOrNaoInformado signs a positive value only when signed=true", () => {
    expect(formatPercentOrNaoInformado(0.123, true)).toBe("+12,3%");
    expect(formatPercentOrNaoInformado(0.123, false)).toBe("12,3%");
  });

  // 🔴 Regression pin. The API returns RATIOS, not percent units:
  // `taxa_conversao = total_vendas / total_leads`. An earlier draft assumed
  // percent units, so a real 5 % conversion rendered as "0,1%" — every
  // number on the page was off by 100. These assert the ×100 conversion
  // with the live shape (69 sales / 1 380 leads = 5 %).
  it("formatPercentOrNaoInformado converts a RATIO to percent, not off by 100", () => {
    expect(formatPercentOrNaoInformado(0.05)).toBe("5,0%");
    expect(formatPercentOrNaoInformado(69 / 1380)).toBe("5,0%");
    expect(formatPercentOrNaoInformado(1)).toBe("100,0%");
  });

  it("formatMultipleOrNaoInformado renders roi as a multiple, not a percentage", () => {
    // roi = valor_vendas / investimento — R$ 2,50 back per R$ 1,00 spent.
    // "+250%" would borrow percentage-CHANGE semantics it does not have.
    expect(formatMultipleOrNaoInformado(2.5)).toBe("2,50×");
    expect(formatMultipleOrNaoInformado(0)).toBe("0,00×");
    expect(formatMultipleOrNaoInformado(null)).toBe("—");
  });

  it("formatCount treats total_leads/total_vendas as never-null, pt-BR thousands", () => {
    expect(formatCount(13329)).toBe("13.329");
    expect(formatCount(null)).toBe("0");
  });

  it("formatDateBR renders YYYY-MM-DD as DD/MM/YYYY", () => {
    expect(formatDateBR("2026-08-13")).toBe("13/08/2026");
  });
});

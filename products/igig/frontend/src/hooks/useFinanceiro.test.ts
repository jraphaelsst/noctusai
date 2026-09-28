/**
 * Tests for `useFinanceiro` — the refetch-unmount + key-change-flicker
 * regression (fleet audit, 2026-08-31). `useFaturas`/`useExcedentes`/
 * `useDRE` are keyed on `competencia` (Category B); `useInadimplentes` is
 * Category A only (static key).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet, post: mockPost } }));

let queryState: Record<string, unknown> = {};
const { capturedOpts } = vi.hoisted(() => ({ capturedOpts: [] as Record<string, unknown>[] }));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn((opts: Record<string, unknown>) => {
    capturedOpts.push(opts);
    return queryState;
  });
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({ ...opts, mutate: vi.fn(), isPending: false }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  useCancelarFatura,
  useDRE,
  useEnviarFatura,
  useExcedentes,
  useFaturas,
  useInadimplentes,
  useMarcarFaturaEnviada,
} from "./useFinanceiro";

beforeEach(() => {
  vi.clearAllMocks();
  capturedOpts.length = 0;
});

describe("useFaturas — loading formula + placeholderData", () => {
  it("REGRESSION: does not report loading when the competência changes but data is present", () => {
    queryState = {
      data: [{ id: "f1", competencia: "2026-08" }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    expect(useFaturas("2026-09").loading).toBe(false);
  });

  it("passes placeholderData", () => {
    useFaturas();
    expect(capturedOpts[0]?.placeholderData).toBeTypeOf("function");
  });
});

describe("useExcedentes — loading formula + placeholderData", () => {
  it("REGRESSION: does not report loading when the competência changes but data is present", () => {
    queryState = {
      data: [{ cliente_id: "c1", excedentes: 2 }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    expect(useExcedentes("2026-09").loading).toBe(false);
  });

  it("passes placeholderData", () => {
    useExcedentes("2026-08");
    expect(capturedOpts[0]?.placeholderData).toBeTypeOf("function");
  });
});

describe("useDRE — loading formula + placeholderData", () => {
  it("REGRESSION: does not report loading mid-refetch once the DRE table is on screen", () => {
    queryState = {
      data: [{ cliente_id: "c1", margem: 100 }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    expect(useDRE().loading).toBe(false);
  });

  it("passes placeholderData", () => {
    useDRE();
    expect(capturedOpts[0]?.placeholderData).toBeTypeOf("function");
  });
});

describe("useCancelarFatura", () => {
  it("posts to the cancelar endpoint", () => {
    const hook = useCancelarFatura() as unknown as { mutationFn: (id: string) => unknown };
    hook.mutationFn("fatura-1");
    expect(mockPost).toHaveBeenCalledWith("/api/financeiro/faturas/fatura-1/cancelar", {});
  });
});

describe("useEnviarFatura", () => {
  it("posts to the enviar endpoint", () => {
    const hook = useEnviarFatura() as unknown as { mutationFn: (id: string) => unknown };
    hook.mutationFn("fatura-1");
    expect(mockPost).toHaveBeenCalledWith("/api/financeiro/faturas/fatura-1/enviar", {});
  });
});

describe("useMarcarFaturaEnviada", () => {
  it("posts to the marcar-enviada endpoint", () => {
    const hook = useMarcarFaturaEnviada() as unknown as { mutationFn: (id: string) => unknown };
    hook.mutationFn("fatura-1");
    expect(mockPost).toHaveBeenCalledWith("/api/financeiro/faturas/fatura-1/marcar-enviada", {});
  });
});

describe("useInadimplentes — loading formula", () => {
  it("REGRESSION: does not report loading mid-refetch once data exists", () => {
    queryState = {
      data: [{ fatura_id: "f1", dias_atraso: 5 }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, atrasadas } = useInadimplentes();
    expect(loading).toBe(false);
    expect(atrasadas).toHaveLength(1);
  });
});

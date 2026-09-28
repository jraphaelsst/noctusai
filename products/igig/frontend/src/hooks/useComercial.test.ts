/**
 * Tests for `useComercial` — the refetch-unmount + key-change-flicker
 * regression (fleet audit, 2026-08-31). `useLeads` is keyed on `status`
 * (Category B); `useOrcamentos` (now `@/hooks/useOrcamentos`) is keyed on its filters too.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet, post: mockPost } }));
vi.mock("@noctusai/lib/components", () => ({ createPipelineHooks: vi.fn(() => ({})) }));

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

import { useLead, useLeads, usePerdidos, useReabrirNegocio } from "./useComercial";
import { useOrcamentos } from "./useOrcamentos";

beforeEach(() => {
  vi.clearAllMocks();
  capturedOpts.length = 0;
});

describe("useLead", () => {
  it("fetches ONE lead by id (achado #11: no longer the org's whole list)", async () => {
    mockGet.mockResolvedValue({ id: "l1", nome: "Ana" });
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    useLead("l1");
    const opts = capturedOpts[0];
    expect(opts?.enabled).toBe(true);
    const queryFn = opts?.queryFn as () => Promise<unknown>;
    await queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/comercial/leads/l1");
  });

  it("disables the query when id is null", () => {
    useLead(null);
    expect(capturedOpts[0]?.enabled).toBe(false);
  });
});

describe("usePerdidos", () => {
  it("fetches the archive by status=perdido", async () => {
    mockGet.mockResolvedValue({ data: [{ id: "n1", status: "perdido" }] });
    queryState = { data: undefined, isPending: true, isFetching: true, isError: false, error: null };
    usePerdidos();
    const queryFn = capturedOpts[0]?.queryFn as () => Promise<unknown>;
    await queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/comercial/negocios", { status: "perdido" });
  });
});

describe("useReabrirNegocio", () => {
  it("POSTs to the reabrir endpoint", async () => {
    // `useMutation`'s mock returns `{...opts, mutate, isPending}` directly —
    // unlike `useQuery`, it does not push into `capturedOpts`.
    mockPost.mockResolvedValue({ data: { id: "n1", status: "aberto" } });
    const resultado = useReabrirNegocio() as unknown as { mutationFn: (id: string) => Promise<unknown> };
    await resultado.mutationFn("n1");
    expect(mockPost).toHaveBeenCalledWith("/api/comercial/negocios/n1/reabrir", {});
  });
});

describe("useLeads — loading formula + placeholderData", () => {
  it("REGRESSION: does not report loading when the status filter changes but data is present", () => {
    queryState = {
      data: [{ id: "lead-1", nome: "Ana", status: "novo" }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, leads } = useLeads("novo");
    expect(loading).toBe(false);
    expect(leads).toHaveLength(1);
  });

  it("keeps placeholderData wired so the status filter does not blank the list", () => {
    useLeads("novo");
    const placeholderData = capturedOpts[0]?.placeholderData as (prev: unknown) => unknown;
    expect(placeholderData).toBeTypeOf("function");
    const previous: unknown[] = [];
    expect(placeholderData(previous)).toBe(previous);
  });
});

describe("useOrcamentos (moved to @/hooks/useOrcamentos) — loading formula", () => {
  it("REGRESSION: never shows a skeleton mid-background-refetch once orçamentos exist", () => {
    queryState = {
      data: [{ id: "o1", titulo: "Social media mensal" }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { showSkeleton, isRefreshing, orcamentos } = useOrcamentos({ aba: "ativos" });
    expect(showSkeleton).toBe(false);
    expect(isRefreshing).toBe(true);
    expect(orcamentos).toHaveLength(1);
  });

  it("keeps placeholderData wired so switching tabs does not blank the list", () => {
    useOrcamentos({ aba: "aceitos" });
    const placeholderData = capturedOpts[0]?.placeholderData as (prev: unknown) => unknown;
    const previous: unknown[] = [];
    expect(placeholderData(previous)).toBe(previous);
  });
});

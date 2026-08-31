/**
 * Tests for `useComercial` — the refetch-unmount + key-change-flicker
 * regression (fleet audit, 2026-08-31). `useLeads` is keyed on `status`
 * (Category B); `useOrcamentos` is Category A only (static key).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet } }));

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

import { useLeads, useOrcamentos } from "./useComercial";

beforeEach(() => {
  vi.clearAllMocks();
  capturedOpts.length = 0;
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

describe("useOrcamentos — loading formula", () => {
  it("REGRESSION: does not report loading mid-background-refetch once orçamentos exist", () => {
    queryState = {
      data: [{ id: "o1", titulo: "Social media mensal" }],
      isPending: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    const { loading, orcamentos } = useOrcamentos();
    expect(loading).toBe(false);
    expect(orcamentos).toHaveLength(1);
  });
});

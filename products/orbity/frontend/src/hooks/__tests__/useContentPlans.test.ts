/** Content plans hooks — helpers (progress / task eligibility) + query states + AI error surface. */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));

vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: mockPost, patch: vi.fn(), delete: vi.fn(), put: vi.fn() } }));
vi.mock("@noctusai/seed/infra", () => ({ useAuthStore: () => ({ user: { id: "u1" } }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

import {
  isTaskEligible,
  planProgress,
  useContentPlans,
  useGenerateAIItems,
  type PlanItem,
} from "@/hooks/useContentPlans";

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

const item = (over: Partial<PlanItem>): PlanItem => ({
  id: "i", org_id: "o", plan_id: "p", order_position: 0, title: "t", description: null, format: null,
  platform: null, post_date: null, due_date: null, caption: null, reference_notes: null,
  status: "planned", task_id: null, post_id: null, created_at: "", updated_at: "", ...over,
});

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});

describe("planProgress", () => {
  it("excludes discarded items from the denominator", () => {
    const p = planProgress({
      items: [
        item({ status: "task_created", task_id: "t1" }),
        item({ status: "planned" }),
        item({ status: "discarded", task_id: "t2" }),
      ],
    });
    expect(p).toEqual({ total: 2, done: 1, percent: 50 });
  });

  it("is 0% for an empty plan, never NaN", () => {
    expect(planProgress({ items: [] })).toEqual({ total: 0, done: 0, percent: 0 });
  });
});

describe("isTaskEligible", () => {
  it("only items without task and not discarded", () => {
    expect(isTaskEligible(item({}))).toBe(true);
    expect(isTaskEligible(item({ task_id: "t" }))).toBe(false);
    expect(isTaskEligible(item({ status: "discarded" }))).toBe(false);
  });
});

describe("useContentPlans", () => {
  it("returns plans with items", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "p1", items: [] }], total: 1, page: 1, page_size: 200 });
    const { result } = renderHook(() => useContentPlans(), { wrapper: wrapper() });
    expect(result.current.isPending).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0].id).toBe("p1");
    expect(mockGet).toHaveBeenCalledWith("/api/content/plans", expect.objectContaining({ page_size: 200 }));
  });

  it("surfaces an error", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useContentPlans(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useGenerateAIItems", () => {
  it("keeps the honest 503 message on the mutation error (no fake items)", async () => {
    mockPost.mockRejectedValue(new Error("IA não configurada. Cadastre a chave"));
    const { result } = renderHook(() => useGenerateAIItems(), { wrapper: wrapper() });
    result.current.mutate({
      planId: "p1",
      params: {
        items_count: 2, period_days: 7, start_date: "2026-11-02", weekdays: [1], platforms: ["instagram"],
        formats: [], pillars: [], allow_sales_cta: true,
      },
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("IA não configurada");
    expect(result.current.data).toBeUndefined();
    expect(mockPost).toHaveBeenCalledWith("/api/content/plans/p1/ai-items", expect.any(Object));
  });
});

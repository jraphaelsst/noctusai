/**
 * Cache writes (wave 2 of the invalidate-only fan-out): each migrated orbity hook puts
 * what it knows into the cache WHILE the request is still in flight / the moment it answers,
 * instead of waiting for a refetch. One representative mutation per hook file.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();
const api = { get: mockGet, post: mockPost, patch: mockPatch, put: mockPut, delete: mockDelete };

vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/seed/infra", () => ({ api, useAuthStore: () => ({ user: { id: "u1" } }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const w = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, w };
}

/** A request that stays in flight until the test answers it. */
function deferred() {
  let answer!: (v: unknown) => void;
  const promise = new Promise((res) => (answer = res));
  return { promise, answer };
}

beforeEach(() => {
  vi.resetAllMocks();
  mockGet.mockReturnValue(new Promise(() => {})); // settle's refetch must never be what the test relies on
});

describe("orbity cache writes", () => {
  it("agenda: an edited event is the server's row in every cached window and the detail", async () => {
    const { qc, w } = setup();
    const ev = { id: "e1", title: "Antigo" };
    qc.setQueryData(["orbity-agenda-events", { from: "a" }], { items: [ev], total: 1, page: 1, page_size: 200 });
    const d = deferred();
    mockPatch.mockReturnValue(d.promise);
    const { useUpdateAgendaEvent } = await import("@/hooks/useAgenda");
    const { result } = renderHook(() => useUpdateAgendaEvent(), { wrapper: w });
    result.current.mutate({ id: "e1", title: "Novo" });
    d.answer({ id: "e1", title: "Novo" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any>(["orbity-agenda-events", { from: "a" }]).items[0].title).toBe("Novo");
    expect(qc.getQueryData<any>(["orbity-agenda-event", "e1"]).title).toBe("Novo");
  });

  it("automacao: a deleted flow leaves the list on the click", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["automation-flows", false], [{ id: "f1" }, { id: "f2" }]);
    mockDelete.mockReturnValue(new Promise(() => {}));
    const { useDeleteFlow } = await import("@/hooks/useAutomacao");
    const { result } = renderHook(() => useDeleteFlow(), { wrapper: w });
    result.current.mutate("f1");
    await waitFor(() => expect(qc.getQueryData(["automation-flows", false])).toEqual([{ id: "f2" }]));
  });

  it("content plans: a new plan is first on page 1 once the POST answers", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["content-plans", undefined], { items: [{ id: "p0" }], total: 1, page: 1, page_size: 200 });
    mockPost.mockResolvedValue({ id: "p1", items: [] });
    const { useCreatePlan } = await import("@/hooks/useContentPlans");
    const { result } = renderHook(() => useCreatePlan(), { wrapper: w });
    result.current.mutate({ title: "Out", month: "2026-10" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const page = qc.getQueryData<any>(["content-plans", undefined]);
    expect(page.items.map((p: { id: string }) => p.id)).toEqual(["p1", "p0"]);
    expect(page.total).toBe(2);
  });

  it("conteudo: a deleted post leaves every cached posts page on the click and the total follows", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["content-posts", { status: "draft" }], { items: [{ id: "x1" }, { id: "x2" }], total: 2, page: 1, page_size: 50 });
    mockDelete.mockReturnValue(new Promise(() => {}));
    const { useDeletePost } = await import("@/hooks/useConteudo");
    const { result } = renderHook(() => useDeletePost(), { wrapper: w });
    result.current.mutate("x1");
    await waitFor(() =>
      expect(qc.getQueryData(["content-posts", { status: "draft" }])).toEqual({ items: [{ id: "x2" }], total: 1, page: 1, page_size: 50 }),
    );
  });

  it("meta ads: a situation change is drawn on the click and rolled back on failure", async () => {
    const { qc, w } = setup();
    const key = ["meta-ads-campaigns", undefined];
    qc.setQueryData(key, { items: [{ id: "c1", situation: "ok" }], total: 1, page: 1, page_size: 50 });
    const d = deferred();
    mockPatch.mockReturnValue(d.promise);
    const { useUpdateSituation } = await import("@/hooks/useMetaAds");
    const { result } = renderHook(() => useUpdateSituation(), { wrapper: w });
    result.current.mutate({ id: "c1", situation: "alert" as never });
    await waitFor(() => expect(qc.getQueryData<any>(key).items[0].situation).toBe("alert"));
    (d as any).answer(Promise.reject(new Error("boom")));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData<any>(key).items[0].situation).toBe("ok");
  });

  it("relatorios: a generated snapshot is first in the snapshots list", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["report-snapshots", "r1"], [{ id: "s0" }]);
    mockPost.mockResolvedValue({ id: "s1" });
    const { useGenerateSnapshot } = await import("@/hooks/useRelatorios");
    const { result } = renderHook(() => useGenerateSnapshot(), { wrapper: w });
    result.current.mutate("r1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData(["report-snapshots", "r1"])).toEqual([{ id: "s1" }, { id: "s0" }]);
  });

  it("tasks: a status change is drawn on the card (list + detail) while the PATCH is in flight", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["orbity-tasks", undefined], { items: [{ id: "t1", status: "todo" }], total: 1, page: 1, page_size: 200 });
    qc.setQueryData(["orbity-task", "t1"], { id: "t1", status: "todo" });
    mockPatch.mockReturnValue(new Promise(() => {}));
    const { useUpdateTaskStatus } = await import("@/hooks/useTasks");
    const { result } = renderHook(() => useUpdateTaskStatus(), { wrapper: w });
    result.current.mutate({ id: "t1", status: "done" });
    await waitFor(() => expect(qc.getQueryData<any>(["orbity-tasks", undefined]).items[0].status).toBe("done"));
    expect(qc.getQueryData<any>(["orbity-task", "t1"]).status).toBe("done");
  });

  it("financial: a requeued charge becomes the server's row (keyed by entry_id)", async () => {
    const { qc, w } = setup();
    qc.setQueryData(["financial-charges", { page: 1 }], { items: [{ entry_id: "c1", generation_status: "failed" }], total: 1, page: 1, page_size: 50 });
    mockPost.mockResolvedValue({ entry_id: "c1", generation_status: "queued" });
    const { useRequeueCharge } = await import("@/hooks/useFinancial");
    const { result } = renderHook(() => useRequeueCharge(), { wrapper: w });
    result.current.mutate("c1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any>(["financial-charges", { page: 1 }]).items[0].generation_status).toBe("queued");
  });

  it("crm: seeding the default stages fills the stages list from the answer", async () => {
    const { qc, w } = setup();
    mockPost.mockResolvedValue([{ id: "s1" }]);
    const { useSeedDefaultStages, crmKeys } = await import("@/hooks/useCrm");
    const { result } = renderHook(() => useSeedDefaultStages(), { wrapper: w });
    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData(crmKeys.stages())).toEqual([{ id: "s1" }]);
  });
});

/**
 * useLeadsImport.test.ts — unit tests for `/api/leads/import/*`.
 *
 * `preview`/`commit` bypass the seed `api` client (JSON-only) and do a raw
 * `fetch` with a `FormData` body, mirroring `useUpload.ts`'s established
 * pattern — these tests mock `@noctusai/seed/infra` (api.get for the batch
 * history list + supabase.auth.getSession for the auth header) and global
 * `fetch` (for preview/commit).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useLeadImportBatches,
  useLeadImportCommit,
  useLeadImportPreview,
} from "./useLeadsImport";

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "tok-123" } } }),
    },
  },
}));

import { api as mockApi } from "@noctusai/seed/infra";
const mockApiGet = mockApi.get as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, Wrapper };
}

const originalFetch = global.fetch;

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  global.fetch = originalFetch;
  vi.clearAllMocks();
});

describe("useLeadImportBatches", () => {
  it("calls GET /api/leads/import/batches (paginated envelope)", async () => {
    mockApiGet.mockResolvedValue({
      data: [
        {
          id: "batch-1",
          filename: "controle.xlsx",
          sheets: 29,
          rows_read: 12195,
          rows_inserted: 12000,
          rows_updated: 100,
          rows_skipped: 50,
          rows_flagged: 45,
          status: "ok",
          erro: null,
          started_at: "2026-07-01T00:00:00Z",
          finished_at: "2026-07-01T00:05:00Z",
        },
      ],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadImportBatches({ page: 1, pageSize: 20 }), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const url: string = mockApiGet.mock.calls[0][0];
    expect(url).toContain("/api/leads/import/batches");
    expect(url).toContain("page=1");
    expect(url).toContain("page_size=20");
    expect(result.current.data?.data[0].status).toBe("ok");
  });
});

describe("useLeadImportPreview", () => {
  it("POSTs multipart form data with an Authorization header and unwraps the envelope", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          filename: "controle.xlsx",
          sheets: ["JULHO_26"],
          rows_read: 100,
          rows_new: 90,
          rows_existing: 5,
          rows_skipped: 5,
          unmapped_origens: [{ alias: "VIVAVREAL", count: 3 }],
          unmapped_corretores: [],
          sample: [],
          warnings: [],
        },
      }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadImportPreview(), { wrapper: Wrapper });
    const file = new File(["dummy"], "controle.xlsx");

    await act(async () => {
      result.current.mutate(file);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/leads/import/preview");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok-123");
    expect(init.body).toBeInstanceOf(FormData);
    expect(result.current.data?.rows_new).toBe(90);
    expect(result.current.data?.unmapped_origens).toEqual([{ alias: "VIVAVREAL", count: 3 }]);
  });

  it("throws a typed error on a non-ok response", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      text: async () => "arquivo invalido",
    }) as unknown as typeof fetch;

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLeadImportPreview(), { wrapper: Wrapper });
    const file = new File(["dummy"], "bad.xlsx");

    await act(async () => {
      result.current.mutate(file);
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("422");
  });
});

describe("useLeadImportCommit", () => {
  it("POSTs to /api/leads/import/commit and invalidates the leads family", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          id: "batch-2",
          filename: "controle.xlsx",
          sheets: 29,
          rows_read: 100,
          rows_inserted: 90,
          rows_updated: 5,
          rows_skipped: 5,
          rows_flagged: 2,
          status: "ok",
          erro: null,
          started_at: "2026-07-01T00:00:00Z",
          finished_at: "2026-07-01T00:01:00Z",
        },
      }),
    }) as unknown as typeof fetch;

    const { qc, Wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useLeadImportCommit(), { wrapper: Wrapper });
    const file = new File(["dummy"], "controle.xlsx");

    await act(async () => {
      result.current.mutate(file);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect((global.fetch as any).mock.calls[0][0]).toContain("/api/leads/import/commit");
    expect(result.current.data?.id).toBe("batch-2");
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["leads"] }));
  });
});

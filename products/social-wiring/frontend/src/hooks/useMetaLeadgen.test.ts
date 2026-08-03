/**
 * Tests for useMetaLeadgen hooks.
 *
 * Verifies:
 *   · every hook hits the exact `/api/meta/leadgen/*` endpoint the router
 *     names, and reads/writes the BARE typed model (no `{data: ...}` unwrap).
 *   · every queryFn/mutationFn resolves to a real object, never `undefined`,
 *     on a bare-null backend response.
 *   · the subscribe/unsubscribe mutations invalidate the subscriptions
 *     query key so every Page row reflects the new state.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, mockDelete, invalidateQueriesMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
  invalidateQueriesMock: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, delete: mockDelete },
}));

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(({ queryFn }: { queryFn: () => unknown }) => ({
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    _queryFn: queryFn,
  }));
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
      mutateAsync: async (vars: unknown) => {
        const result = await mutationFn(vars);
        onSuccess?.(result, vars);
        return result;
      },
      isPending: false,
      isError: false,
      error: null,
      _mutationFn: mutationFn,
    }),
  );
  const useQueryClient = vi.fn(() => ({ invalidateQueries: invalidateQueriesMock }));
  return { useQuery, useMutation, useQueryClient };
});

import {
  useLeadgenSubscriptions,
  useSubscribeLeadgenPages,
  useUnsubscribeLeadgenPage,
  useLeadgenEvents,
} from "./useMetaLeadgen";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useLeadgenSubscriptions", () => {
  it("GETs /api/meta/leadgen/subscriptions and returns the bare model", async () => {
    const payload = {
      pages: [{ page_id: "p1", page_name: "Loja", subscribed: true, subscribed_fields: ["leadgen"], app_id: "a1" }],
      callback_url: "https://social.noctusai.com/api/meta/leadgen/webhook",
      verify_token_configured: true,
      gated: false,
      reason: null,
    };
    mockGet.mockResolvedValue(payload);
    const hook = useLeadgenSubscriptions() as any;
    const result = await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/meta/leadgen/subscriptions");
    expect(result).toEqual(payload);
  });

  it("never returns undefined from queryFn on a bare-null response", async () => {
    mockGet.mockResolvedValue(null);
    const hook = useLeadgenSubscriptions() as any;
    const result = await hook._queryFn();
    expect(result).toEqual({
      pages: [],
      callback_url: "",
      verify_token_configured: false,
      gated: false,
      reason: null,
    });
  });
});

describe("useLeadgenEvents", () => {
  it("GETs /api/meta/leadgen/events with the limit query param", async () => {
    mockGet.mockResolvedValue({ counts: { received: 3 }, last_received_at: null, events: [] });
    const hook = useLeadgenEvents(50) as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/meta/leadgen/events?limit=50");
  });

  it("defaults limit to 20", async () => {
    mockGet.mockResolvedValue({ counts: {}, last_received_at: null, events: [] });
    const hook = useLeadgenEvents() as any;
    await hook._queryFn();
    expect(mockGet).toHaveBeenCalledWith("/api/meta/leadgen/events?limit=20");
  });

  it("never returns undefined from queryFn on a bare-null response", async () => {
    mockGet.mockResolvedValue(null);
    const hook = useLeadgenEvents() as any;
    const result = await hook._queryFn();
    expect(result).toEqual({ counts: {}, last_received_at: null, events: [] });
  });
});

describe("useSubscribeLeadgenPages", () => {
  it("POSTs page_ids and invalidates the subscriptions query on success", async () => {
    mockPost.mockResolvedValue({ results: [{ page_id: "p1", ok: true, error: null }] });
    const hook = useSubscribeLeadgenPages() as any;
    await hook.mutateAsync(["p1"]);
    expect(mockPost).toHaveBeenCalledWith("/api/meta/leadgen/subscriptions", {
      page_ids: ["p1"],
    });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ["meta-leadgen", "subscriptions"],
    });
  });

  it("sends page_ids: null for the 'subscribe all' action", async () => {
    mockPost.mockResolvedValue({ results: [] });
    const hook = useSubscribeLeadgenPages() as any;
    await hook.mutateAsync(null);
    expect(mockPost).toHaveBeenCalledWith("/api/meta/leadgen/subscriptions", {
      page_ids: null,
    });
  });

  it("never returns undefined from mutationFn on a bare-null response", async () => {
    mockPost.mockResolvedValue(null);
    const hook = useSubscribeLeadgenPages() as any;
    const result = await hook.mutateAsync(["p1"]);
    expect(result).toEqual({ results: [] });
  });
});

describe("useUnsubscribeLeadgenPage", () => {
  it("DELETEs the page's subscription and invalidates the subscriptions query", async () => {
    mockDelete.mockResolvedValue({ page_id: "p1", ok: true, error: null });
    const hook = useUnsubscribeLeadgenPage() as any;
    await hook.mutateAsync("p1");
    expect(mockDelete).toHaveBeenCalledWith("/api/meta/leadgen/subscriptions/p1");
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ["meta-leadgen", "subscriptions"],
    });
  });

  it("URL-encodes the page id", async () => {
    mockDelete.mockResolvedValue({ page_id: "p/1", ok: true, error: null });
    const hook = useUnsubscribeLeadgenPage() as any;
    await hook.mutateAsync("p/1");
    expect(mockDelete).toHaveBeenCalledWith("/api/meta/leadgen/subscriptions/p%2F1");
  });

  it("never returns undefined from mutationFn on a bare-null response", async () => {
    mockDelete.mockResolvedValue(null);
    const hook = useUnsubscribeLeadgenPage() as any;
    const result = await hook.mutateAsync("p1");
    expect(result).toEqual({
      page_id: "p1",
      ok: false,
      error: "resposta vazia do servidor",
    });
  });
});

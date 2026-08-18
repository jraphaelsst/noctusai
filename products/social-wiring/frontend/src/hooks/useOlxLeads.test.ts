/**
 * Tests for the Grupo OLX portal-lead hooks.
 *
 * The two that matter:
 *   · `loading` is `isPending || isFetching`, never `isLoading` — a card
 *     that renders "no deliveries yet" during a background refetch reads
 *     as "the integration is dead" at the moment it is working.
 *   · `stuck` names the statuses an operator must act on (`unresolved`
 *     and `error`), because an unresolved lead is a real enquiry nobody
 *     has been told about.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, invalidateQueriesMock, useQueryMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  invalidateQueriesMock: vi.fn(),
  useQueryMock: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost },
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
      mutateAsync: async (vars: unknown) => {
        const result = await mutationFn(vars);
        onSuccess?.(result, vars);
        return result;
      },
      isPending: false,
      _mutationFn: mutationFn,
    }),
  );
  const useQueryClient = vi.fn(() => ({ invalidateQueries: invalidateQueriesMock }));
  return { useQuery, useMutation, useQueryClient };
});

import { useOlxBackfill, useOlxEvents, type OlxLeadEvent } from "./useOlxLeads";

function event(overrides: Partial<OlxLeadEvent> = {}): OlxLeadEvent {
  return {
    id: "lead-1",
    org_id: "org-1",
    client_listing_id: "a40171",
    lead_origin: "Grupo OLX",
    lead_type: "CONTACT_CHAT",
    status: "processed",
    error: null,
    attempts: 1,
    received_at: "2026-08-17T10:00:00Z",
    processed_at: "2026-08-17T10:00:01Z",
    ...overrides,
  };
}

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

describe("useOlxEvents", () => {
  it("GETs /api/portals/olx/events with the requested limit", async () => {
    mockGet.mockResolvedValue({ events: [], counts: {} });
    const hook = useOlxEvents(25) as any;

    await hook._queryFn();

    expect(mockGet).toHaveBeenCalledWith("/api/portals/olx/events?limit=25");
  });

  it("reports loading during a background refetch, not just the first load", () => {
    // The lying-loading-state trap: isPending false, isFetching true.
    queryState({ isPending: false, isFetching: true, data: { events: [], counts: {} } });

    const hook = useOlxEvents() as any;

    expect(hook.loading).toBe(true);
    expect(hook.isEmpty).toBe(false);
  });

  it("reports loading on the first load", () => {
    queryState({ isPending: true, isFetching: true });

    expect((useOlxEvents() as any).loading).toBe(true);
  });

  it("is empty only when settled with no events", () => {
    queryState({ isPending: false, isFetching: false, data: { events: [], counts: {} } });

    const hook = useOlxEvents() as any;

    expect(hook.isEmpty).toBe(true);
    expect(hook.loading).toBe(false);
  });

  it("counts unresolved and error deliveries as stuck", () => {
    queryState({
      data: {
        events: [
          event({ id: "a", status: "processed" }),
          event({ id: "b", status: "unresolved" }),
          event({ id: "c", status: "error" }),
          event({ id: "d", status: "ignored" }),
        ],
        counts: { processed: 1, unresolved: 1, error: 1, ignored: 1 },
      },
    });

    const hook = useOlxEvents() as any;

    expect(hook.stuck.map((e: OlxLeadEvent) => e.id)).toEqual(["b", "c"]);
  });

  it("does not treat an ignored delivery as stuck", () => {
    // `ignored` is a decision we made (unparseable body), not a lead
    // waiting on someone — surfacing it as actionable would train the
    // operator to ignore the panel.
    queryState({
      data: { events: [event({ status: "ignored" })], counts: { ignored: 1 } },
    });

    expect((useOlxEvents() as any).stuck).toEqual([]);
  });

  it("tolerates a response with no events array", () => {
    queryState({ data: undefined });

    const hook = useOlxEvents() as any;

    expect(hook.events).toEqual([]);
    expect(hook.stuck).toEqual([]);
  });
});

describe("useOlxBackfill", () => {
  it("POSTs the backfill route and invalidates both families", async () => {
    mockPost.mockResolvedValue({ ingested: 3, skipped_existing: 1, errors: [] });
    const hook = useOlxBackfill() as any;

    const result = await hook.mutateAsync();

    expect(mockPost).toHaveBeenCalledWith("/api/portals/olx/backfill", {});
    expect(result.ingested).toBe(3);
    // The projection writes into `leads`, so that cache is stale too —
    // invalidating only the OLX family would leave the leads table showing
    // a pre-backfill count.
    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ["portals", "olx"],
    });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ["leads"] });
  });
});

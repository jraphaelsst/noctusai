/**
 * Tests for the ImovelWeb portal-lead hooks.
 *
 * Four properties, each one a bug an operator would otherwise meet in
 * production:
 *
 *   · `loading` is `isPending || isFetching`, never `isLoading` — a card
 *     that renders "no deliveries yet" during a background refetch reads
 *     as "the integration is dead" at the moment it is working.
 *   · `stuck` names the statuses someone must act on.
 *   · `deliversNothing` surfaces a registration that is subscribed to no
 *     events — legal to the vendor, silent, and the likeliest fault here.
 *   · `reconcileShare` is null with no deliveries, not 0. Zero would read
 *     as "the fast path is working" when nothing has arrived at all.
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

import {
  useImovelWebBackfill,
  useImovelWebCallbackConfig,
  useImovelWebEvents,
  useImovelWebReconcile,
  useRegisterImovelWebCallback,
  type ImovelWebLeadEvent,
} from "./useImovelWebLeads";

function event(overrides: Partial<ImovelWebLeadEvent> = {}): ImovelWebLeadEvent {
  return {
    id: "evt-1",
    org_id: "org-1",
    event_type: "CONTACTO_MENSAJE",
    codigo_imobiliaria: "noc-org-demo",
    client_listing_id: "AP-1024",
    lead_origin: "Imovelweb",
    callback_language: "EN2",
    source: "callback",
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

describe("useImovelWebEvents", () => {
  it("GETs the events route with the requested limit", async () => {
    mockGet.mockResolvedValue({ events: [], counts: {}, bySource: {} });
    const hook = useImovelWebEvents(25) as any;

    await hook._queryFn();

    expect(mockGet).toHaveBeenCalledWith("/api/portals/imovelweb/events?limit=25");
  });

  it("reports loading during a background refetch, not just the first load", () => {
    // The lying-loading-state trap: isPending false, isFetching true.
    queryState({
      isPending: false,
      isFetching: true,
      data: { events: [], counts: {}, bySource: {} },
    });

    const hook = useImovelWebEvents() as any;

    expect(hook.loading).toBe(true);
    expect(hook.isEmpty).toBe(false);
  });

  it("reports loading on the first load", () => {
    queryState({ isPending: true, isFetching: true });

    expect((useImovelWebEvents() as any).loading).toBe(true);
  });

  it("is empty only when settled with no events", () => {
    queryState({
      isPending: false,
      isFetching: false,
      data: { events: [], counts: {}, bySource: {} },
    });

    const hook = useImovelWebEvents() as any;

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
        ],
        counts: {},
        bySource: { callback: 3, reconcile: 0 },
      },
    });

    const hook = useImovelWebEvents() as any;

    expect(hook.stuck.map((e: ImovelWebLeadEvent) => e.id)).toEqual(["b", "c"]);
  });

  it("computes the reconcile share of recent deliveries", () => {
    // A rising share is the operator-visible symptom of missing the
    // vendor's 1.5-second budget: the leads still arrive, just late and
    // by the slower path.
    queryState({
      data: { events: [event()], counts: {}, bySource: { callback: 3, reconcile: 1 } },
    });

    expect((useImovelWebEvents() as any).reconcileShare).toBeCloseTo(0.25);
  });

  it("reports a null reconcile share when nothing has arrived", () => {
    // NOT 0 — that would read as "the fast path is working" when there is
    // simply no data to say anything about.
    queryState({
      data: { events: [], counts: {}, bySource: { callback: 0, reconcile: 0 } },
    });

    expect((useImovelWebEvents() as any).reconcileShare).toBeNull();
  });

  it("tolerates a response with no bySource block", () => {
    queryState({ data: { events: [event()], counts: {} } });

    const hook = useImovelWebEvents() as any;

    expect(hook.bySource).toEqual({ callback: 0, reconcile: 0 });
    expect(hook.reconcileShare).toBeNull();
  });
});

describe("useImovelWebCallbackConfig", () => {
  it("GETs the callback route", async () => {
    mockGet.mockResolvedValue({ config: null, subscriptions: [] });
    const hook = useImovelWebCallbackConfig() as any;

    await hook._queryFn();

    expect(mockGet).toHaveBeenCalledWith("/api/portals/imovelweb/callback");
  });

  it("surfaces a registration that delivers nothing", () => {
    // Registered, subscribed to no events: the vendor accepts it and then
    // delivers nothing, silently, while every other indicator stays green.
    queryState({
      data: {
        config: { url: "https://noc.example.com/x", subscriptions: [] },
        subscriptions: [],
        delivers_nothing: true,
        problems: [],
      },
    });

    expect((useImovelWebCallbackConfig() as any).deliversNothing).toBe(true);
  });

  it("distinguishes unregistered from registered-but-empty", () => {
    queryState({
      data: { config: null, subscriptions: [], delivers_nothing: true, problems: [] },
    });

    expect((useImovelWebCallbackConfig() as any).isUnregistered).toBe(true);
  });

  it("is not unregistered before the first response arrives", () => {
    queryState({ isPending: true, isFetching: true, data: undefined });

    expect((useImovelWebCallbackConfig() as any).isUnregistered).toBe(false);
  });
});

describe("useRegisterImovelWebCallback", () => {
  it("always sends confirm=true", async () => {
    // The backend requires it; a component that had to remember would
    // eventually forget. The user's confirmation is the dialog.
    mockPost.mockResolvedValue({ registered: true });
    const mutation = useRegisterImovelWebCallback() as any;

    await mutation.mutateAsync({ publicBaseUrl: "https://noc.example.com" });

    expect(mockPost).toHaveBeenCalledWith("/api/portals/imovelweb/callback/register", {
      publicBaseUrl: "https://noc.example.com",
      confirm: true,
    });
  });

  it("invalidates the callback config after registering", async () => {
    mockPost.mockResolvedValue({ registered: true });
    const mutation = useRegisterImovelWebCallback() as any;

    await mutation.mutateAsync({});

    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: ["portals", "imovelweb", "callback"],
    });
  });
});

describe("useImovelWebBackfill", () => {
  it("POSTs the backfill route and invalidates both families", async () => {
    mockPost.mockResolvedValue({ ingested: 2, skipped_existing: 0, errors: [] });
    const mutation = useImovelWebBackfill() as any;

    await mutation.mutateAsync();

    expect(mockPost).toHaveBeenCalledWith("/api/portals/imovelweb/backfill", {});
    // The projection writes into `leads`, so that family is stale too.
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ["leads"] });
  });
});

describe("useImovelWebReconcile", () => {
  it("POSTs the reconcile route", async () => {
    mockPost.mockResolvedValue({ agencies: 1, recovered: 0, results: [] });
    const mutation = useImovelWebReconcile() as any;

    await mutation.mutateAsync();

    expect(mockPost).toHaveBeenCalledWith("/api/portals/imovelweb/reconcile", {});
  });
});

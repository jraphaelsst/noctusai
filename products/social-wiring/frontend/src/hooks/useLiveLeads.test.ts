/**
 * Tests for `useLiveLeads` — the "appears without a refresh" requirement.
 *
 * The whole point of this hook is what it must NOT do: it must not refetch.
 * An `invalidateQueries` on the lead list would reintroduce the network round
 * trip the SSE stream removes and flash the list's loading state on every
 * arrival. So the assertions here are as much about the absence of a refetch
 * as about the presence of the new row.
 *
 * Also pinned: the de-dup guard. The seed's realtime contract explicitly says
 * a resumed connection may redeliver an event the client already applied, so
 * a handler that is not idempotent shows the same lead twice after any blip.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { setQueriesDataMock, invalidateQueriesMock, realtimeMock } = vi.hoisted(() => ({
  setQueriesDataMock: vi.fn(),
  invalidateQueriesMock: vi.fn(),
  realtimeMock: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  // The stream authenticates with the session's bearer token — an
  // `EventSource` could not send one, which is why every /stream request 401'd
  // in production until 2026-08-25. Asserted below, not just mocked away.
  getAuthToken: vi.fn(async () => "test-token"),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(() => ({ data: undefined, isPending: false, isFetching: false })),
  useMutation: vi.fn(() => ({ mutate: vi.fn() })),
  useQueryClient: () => ({
    setQueriesData: setQueriesDataMock,
    invalidateQueries: invalidateQueriesMock,
  }),
}));

// Capture what the hook hands the seed transport, and expose the `onEvent`
// callback so a frame can be delivered without a real EventSource.
vi.mock("@noctusai/lib", () => ({
  useRealtimeStream: (url: string | null, opts: any) => {
    realtimeMock(url, opts);
    return { status: "open", lastEventId: null };
  },
}));

vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return { ...actual, useCallback: (fn: any) => fn };
});

import { useLiveLeads, LEADGEN_EVENTS } from "./useMetaLeadgen";

function lastOptions() {
  return realtimeMock.mock.calls[realtimeMock.mock.calls.length - 1][1];
}
function lastUrl() {
  return realtimeMock.mock.calls[realtimeMock.mock.calls.length - 1][0];
}

const LEAD = {
  id: "lead-1",
  full_name: "Fulana da Silva",
  email: "fulana@example.com",
  phone: "+5511999999999",
  form_id: "form-1",
  form_name: "Formulário A",
  campaign_name: "Campanha X",
  platform: "fb",
  created_time: "2026-08-04T12:00:00Z",
};

beforeEach(() => {
  setQueriesDataMock.mockReset();
  invalidateQueriesMock.mockReset();
  realtimeMock.mockReset();
});

describe("useLiveLeads", () => {
  it("subscribes to the org stream and registers its own event vocabulary", () => {
    useLiveLeads(true);
    expect(lastUrl()).toBe("/api/meta/leadgen/stream");
    // 🔴 EventSource only delivers a named event to a listener registered for
    // that exact name — omitting this makes the stream silently dead.
    expect(lastOptions().events).toEqual(LEADGEN_EVENTS);
  });

  it("hands the transport a token getter, so the stream can authenticate", async () => {
    // 🔴 Regression pin. `useRealtimeStream` used to open an `EventSource`,
    // which cannot send an `Authorization` header at all — so this feed 401'd
    // on every attempt in production and no lead ever arrived live. The hook
    // must forward a token getter, and it must actually resolve a token.
    useLiveLeads(true);

    const { getAuthToken } = lastOptions();
    expect(typeof getAuthToken).toBe("function");
    await expect(getAuthToken()).resolves.toBe("test-token");
  });

  it("passes a null url when disabled, so no connection is held open", () => {
    useLiveLeads(false);
    expect(lastUrl()).toBeNull();
  });

  it("PREPENDS the new lead into the cached list without refetching it", () => {
    useLiveLeads(true);
    lastOptions().onEvent({ event: "lead.new", payload: LEAD });

    expect(setQueriesDataMock).toHaveBeenCalledTimes(1);
    const [key, updater] = setQueriesDataMock.mock.calls[0];
    expect(key).toEqual({ queryKey: ["meta-ads", "lead-records"] });

    const next = updater({
      form_id: "form-1",
      gated: false,
      reason: null,
      source: "db",
      data: [{ id: "older", created_time: null, field_data: [] }],
    });
    expect(next.data).toHaveLength(2);
    expect(next.data[0].id).toBe("lead-1");
    expect(next.data[1].id).toBe("older");

    // The lead list itself must never be invalidated — only the delivery
    // health counter, which is a different query.
    const invalidated = invalidateQueriesMock.mock.calls.map((c) => c[0].queryKey);
    expect(invalidated).toEqual([["meta-leadgen", "events"]]);
  });

  it("carries the contact fields through so the row renders a name, not a blank", () => {
    useLiveLeads(true);
    lastOptions().onEvent({ event: "lead.new", payload: LEAD });
    const updater = setQueriesDataMock.mock.calls[0][1];
    const next = updater({ form_id: "form-1", data: [], gated: false, reason: null, source: "db" });
    const names = next.data[0].field_data.map((f: any) => f.name);
    expect(names).toEqual(["full_name", "email", "phone_number"]);
    expect(next.data[0].field_data[0].values).toEqual(["Fulana da Silva"]);
  });

  it("is idempotent — a redelivered event does not duplicate the row", () => {
    useLiveLeads(true);
    lastOptions().onEvent({ event: "lead.new", payload: LEAD });
    const updater = setQueriesDataMock.mock.calls[0][1];
    const already = {
      form_id: "form-1",
      gated: false,
      reason: null,
      source: "db" as const,
      data: [{ id: "lead-1", created_time: null, field_data: [] }],
    };
    expect(updater(already)).toBe(already);
  });

  it("leaves another form's cached list untouched", () => {
    useLiveLeads(true);
    lastOptions().onEvent({ event: "lead.new", payload: LEAD });
    const updater = setQueriesDataMock.mock.calls[0][1];
    const otherForm = {
      form_id: "form-2",
      gated: false,
      reason: null,
      source: "db" as const,
      data: [],
    };
    expect(updater(otherForm)).toBe(otherForm);
  });

  it("ignores unrelated events and malformed payloads rather than corrupting the cache", () => {
    useLiveLeads(true);
    const onEvent = lastOptions().onEvent;
    onEvent({ event: "heartbeat", payload: {} });
    onEvent({ event: "lead.new", payload: {} }); // no id
    expect(setQueriesDataMock).not.toHaveBeenCalled();
  });
});

/**
 * OlxWebhookCard — the four states, and the one that matters.
 *
 * `unresolved` deliveries are real enquiries nobody has been told about,
 * so the card has to surface them loudly and explain WHY they are parked
 * (we refuse to guess which client they belong to). The empty state has
 * to read as "expected before homologation", not as a failure — an
 * operator who reads an honest empty state as breakage goes and files a
 * bug against a working integration.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const { useOlxEventsMock, useOlxBackfillMock, mutateAsyncMock } = vi.hoisted(() => ({
  useOlxEventsMock: vi.fn(),
  useOlxBackfillMock: vi.fn(),
  mutateAsyncMock: vi.fn(),
}));

vi.mock("@/hooks/useOlxLeads", () => ({
  useOlxEvents: useOlxEventsMock,
  useOlxBackfill: useOlxBackfillMock,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import OlxWebhookCard from "./OlxWebhookCard";

function event(over: Record<string, unknown> = {}) {
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
    ...over,
  };
}

function state(over: Record<string, unknown> = {}) {
  useOlxEventsMock.mockReturnValue({
    events: [],
    counts: {},
    stuck: [],
    loading: false,
    isEmpty: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  state();
  useOlxBackfillMock.mockReturnValue({
    mutateAsync: mutateAsyncMock,
    isPending: false,
  });
});

describe("OlxWebhookCard", () => {
  it("shows the receiver URL the operator has to hand to OLX", () => {
    render(<OlxWebhookCard />);

    expect(screen.getByTestId("olx-receiver-url").textContent).toContain(
      "/api/portals/olx/leads",
    );
  });

  it("renders the loading state", () => {
    state({ loading: true });

    render(<OlxWebhookCard />);

    expect(screen.getByTestId("olx-events-loading")).toBeTruthy();
  });

  it("renders the error state", () => {
    state({ isError: true, error: new Error("boom") });

    render(<OlxWebhookCard />);

    expect(screen.getByTestId("olx-events-error")).toBeTruthy();
  });

  it("explains that an empty inbox is expected before homologation", () => {
    state({ isEmpty: true });

    render(<OlxWebhookCard />);

    expect(screen.getByTestId("olx-events-empty").textContent).toContain(
      "homologação",
    );
  });

  it("surfaces stuck deliveries and says why they are parked", () => {
    state({
      events: [event({ status: "unresolved", org_id: null })],
      counts: { unresolved: 1 },
      stuck: [event({ status: "unresolved", org_id: null })],
    });

    render(<OlxWebhookCard />);

    const banner = screen.getByTestId("olx-stuck-banner");
    expect(banner.textContent).toContain("1 lead(s) aguardando atenção");
    // The reason matters as much as the count: without it the operator
    // reads "unresolved" as a bug rather than a decision we made.
    expect(banner.textContent).toContain("suposição");
  });

  it("confirms health when nothing is stuck", () => {
    state({
      events: [event()],
      counts: { processed: 1 },
      stuck: [],
    });

    render(<OlxWebhookCard />);

    expect(screen.getByTestId("olx-healthy")).toBeTruthy();
    expect(screen.queryByTestId("olx-stuck-banner")).toBeNull();
  });

  it("lists recent deliveries with their listing id", () => {
    state({ events: [event()], counts: { processed: 1 } });

    render(<OlxWebhookCard />);

    const list = screen.getByTestId("olx-events-list");
    expect(list.textContent).toContain("lead-1");
    expect(list.textContent).toContain("a40171");
  });

  it("never renders the empty state while data is present", () => {
    // The lying-loading-state failure mode, one layer up: "no deliveries"
    // must never paint over deliveries that exist.
    state({ events: [event()], counts: { processed: 1 }, isEmpty: false });

    render(<OlxWebhookCard />);

    expect(screen.queryByTestId("olx-events-empty")).toBeNull();
    expect(screen.getByTestId("olx-events-success")).toBeTruthy();
  });
});

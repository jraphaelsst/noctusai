/**
 * ImovelWebWebhookCard — the four states, plus the two silent failures.
 *
 * The loading/empty/error/success set is table stakes. What this card
 * exists for is the pair of registration faults that produce NO error
 * anywhere: a callback subscribed to no events (the vendor accepts it and
 * sends nothing) and a registered URL that is not ours (the vendor
 * believes it delivered). If this card does not show them, nothing does.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const {
  useEventsMock,
  useCallbackMock,
  useRegisterMock,
  useBackfillMock,
  useReconcileMock,
} = vi.hoisted(() => ({
  useEventsMock: vi.fn(),
  useCallbackMock: vi.fn(),
  useRegisterMock: vi.fn(),
  useBackfillMock: vi.fn(),
  useReconcileMock: vi.fn(),
}));

vi.mock("@/hooks/useImovelWebLeads", () => ({
  useImovelWebEvents: useEventsMock,
  useImovelWebCallbackConfig: useCallbackMock,
  useRegisterImovelWebCallback: useRegisterMock,
  useImovelWebBackfill: useBackfillMock,
  useImovelWebReconcile: useReconcileMock,
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import ImovelWebWebhookCard from "./ImovelWebWebhookCard";

function event(over: Record<string, unknown> = {}) {
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
    ...over,
  };
}

function eventsState(over: Record<string, unknown> = {}) {
  useEventsMock.mockReturnValue({
    events: [],
    counts: {},
    stuck: [],
    bySource: { callback: 0, reconcile: 0 },
    reconcileShare: null,
    loading: false,
    isEmpty: true,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  });
}

function callbackState(over: Record<string, unknown> = {}) {
  useCallbackMock.mockReturnValue({
    config: null,
    subscriptions: [],
    deliversNothing: false,
    problems: [],
    isUnregistered: true,
    loading: false,
    isError: false,
    ...over,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  eventsState();
  callbackState();
  useRegisterMock.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  useBackfillMock.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  useReconcileMock.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

describe("the four states", () => {
  it("renders a skeleton while loading", () => {
    eventsState({ loading: true, isEmpty: false });

    render(<ImovelWebWebhookCard />);

    expect(screen.getByTestId("imovelweb-events-loading")).toBeTruthy();
  });

  it("renders an honest empty state", () => {
    // Must not read as breakage: an operator who reads an honest empty
    // state as a failure files a bug against a working integration.
    render(<ImovelWebWebhookCard />);

    expect(screen.getByTestId("imovelweb-events-empty")).toBeTruthy();
  });

  it("renders the error state", () => {
    eventsState({ isError: true, isEmpty: false, error: new Error("boom") });

    render(<ImovelWebWebhookCard />);

    expect(screen.getByTestId("imovelweb-events-error")).toBeTruthy();
  });

  it("renders deliveries when they exist", () => {
    eventsState({ events: [event()], isEmpty: false, counts: { processed: 1 } });

    render(<ImovelWebWebhookCard />);

    expect(screen.getByTestId("imovelweb-events-success")).toBeTruthy();
    expect(screen.getByTestId("imovelweb-healthy")).toBeTruthy();
  });
});

describe("the silent registration failures", () => {
  it("shows no-subscriptions in red, with the reason", () => {
    // The vendor accepts this configuration and then delivers nothing,
    // with no error anywhere. This card is the only place it surfaces.
    callbackState({
      config: { url: "https://noc.example.com/api/portals/imovelweb/leads" },
      subscriptions: [],
      deliversNothing: true,
      isUnregistered: false,
    });

    render(<ImovelWebWebhookCard />);

    const banner = screen.getByTestId("imovelweb-no-subscriptions");
    expect(banner).toBeTruthy();
    expect(banner.textContent).toMatch(/nada será entregue/i);
  });

  it("flags a registered URL that is not ours", () => {
    callbackState({
      config: { url: "https://old-tunnel.example.com/hook" },
      subscriptions: ["CONTACTO"],
      isUnregistered: false,
    });

    render(<ImovelWebWebhookCard />);

    const mismatch = screen.getByTestId("imovelweb-url-mismatch");
    expect(mismatch.textContent).toContain("https://old-tunnel.example.com/hook");
  });

  it("does not flag a matching URL", () => {
    callbackState({
      config: { url: `${window.location.origin}/api/portals/imovelweb/leads` },
      subscriptions: ["CONTACTO"],
      isUnregistered: false,
    });

    render(<ImovelWebWebhookCard />);

    expect(screen.queryByTestId("imovelweb-url-mismatch")).toBeNull();
  });

  it("treats a trailing slash as the same URL", () => {
    callbackState({
      config: { url: `${window.location.origin}/api/portals/imovelweb/leads/` },
      subscriptions: ["CONTACTO"],
      isUnregistered: false,
    });

    render(<ImovelWebWebhookCard />);

    expect(screen.queryByTestId("imovelweb-url-mismatch")).toBeNull();
  });

  it("does not paint unregistered as a mismatch", () => {
    // "Not set up yet" is not a fault. Colouring it red would make
    // first-time setup look broken.
    render(<ImovelWebWebhookCard />);

    expect(screen.getByTestId("imovelweb-callback-unregistered")).toBeTruthy();
    expect(screen.queryByTestId("imovelweb-url-mismatch")).toBeNull();
  });

  it("says a failed read is not a failed registration", () => {
    callbackState({ isError: true, isUnregistered: false });

    render(<ImovelWebWebhookCard />);

    const node = screen.getByTestId("imovelweb-callback-error");
    expect(node.textContent).toMatch(/não significa que o registro está errado/i);
  });

  it("shows a skeleton while the config loads", () => {
    callbackState({ loading: true });

    render(<ImovelWebWebhookCard />);

    expect(screen.getByTestId("imovelweb-callback-loading")).toBeTruthy();
  });
});

describe("stuck deliveries", () => {
  it("leads with the stuck banner and explains why they are parked", () => {
    eventsState({
      events: [event({ status: "unresolved" })],
      stuck: [event({ status: "unresolved" })],
      isEmpty: false,
    });

    render(<ImovelWebWebhookCard />);

    const banner = screen.getByTestId("imovelweb-stuck-banner");
    expect(banner.textContent).toMatch(/nunca é atribuído por suposição/i);
  });

  it("shows no stuck banner when everything processed", () => {
    eventsState({ events: [event()], isEmpty: false });

    render(<ImovelWebWebhookCard />);

    expect(screen.queryByTestId("imovelweb-stuck-banner")).toBeNull();
  });
});

describe("the reconcile share", () => {
  it("reports the delivery split", () => {
    eventsState({
      events: [event()],
      isEmpty: false,
      bySource: { callback: 9, reconcile: 1 },
      reconcileShare: 0.1,
    });

    render(<ImovelWebWebhookCard />);

    expect(screen.getByTestId("imovelweb-source-split").textContent).toContain(
      "9 por webhook",
    );
  });

  it("warns when too many leads had to be pulled", () => {
    // The operator-visible symptom of missing the vendor's 1.5s budget:
    // the leads still arrive, just by the slow path.
    eventsState({
      events: [event()],
      isEmpty: false,
      bySource: { callback: 5, reconcile: 5 },
      reconcileShare: 0.5,
    });

    render(<ImovelWebWebhookCard />);

    expect(screen.getByTestId("imovelweb-source-split").textContent).toMatch(
      /1,5s/,
    );
  });

  it("says nothing about the split when nothing has arrived", () => {
    eventsState({ events: [event()], isEmpty: false, reconcileShare: null });

    render(<ImovelWebWebhookCard />);

    expect(screen.queryByTestId("imovelweb-source-split")).toBeNull();
  });
});

describe("the integrator-wide write", () => {
  it("names the blast radius before registering", async () => {
    const confirmSpy = vi
      .spyOn(window, "confirm")
      .mockImplementation(() => false);
    const mutateAsync = vi.fn();
    useRegisterMock.mockReturnValue({ mutateAsync, isPending: false });

    render(<ImovelWebWebhookCard />);
    screen.getByTestId("imovelweb-register").click();

    expect(confirmSpy).toHaveBeenCalled();
    expect(confirmSpy.mock.calls[0][0]).toMatch(/TODAS as imobiliárias/);
    // Declining must perform NO write.
    expect(mutateAsync).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

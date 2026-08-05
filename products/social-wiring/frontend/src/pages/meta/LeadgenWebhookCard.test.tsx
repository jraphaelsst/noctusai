/**
 * LeadgenWebhookCard.test.tsx — the Meta Lead-Ads webhook subscription card.
 *
 * Mocks every hook + UI primitive (no real TanStack Query provider needed),
 * mirroring the IgVisaoGeral.test.tsx conventions used across this product.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseLeadgenSubscriptions = vi.fn();
const mockUseSubscribeLeadgenPages = vi.fn();
const mockUseUnsubscribeLeadgenPage = vi.fn();
const mockUseLeadgenEvents = vi.fn();
const mockUseSetPageClient = vi.fn();

vi.mock("@/hooks/useMetaLeadgen", () => ({
  useLeadgenSubscriptions: mockUseLeadgenSubscriptions,
  useSubscribeLeadgenPages: mockUseSubscribeLeadgenPages,
  useUnsubscribeLeadgenPage: mockUseUnsubscribeLeadgenPage,
  useLeadgenEvents: mockUseLeadgenEvents,
  useSetPageClient: mockUseSetPageClient,
}));

// `useClients` calls TanStack's `useQuery` directly; without a provider it
// throws and takes the whole card down. Two real clients so the per-Page
// attribution selector has something to render.
vi.mock("@/hooks/useClients", () => ({
  useClients: () => ({
    data: [
      { id: "client-one", name: "One Consultoria" },
      { id: "client-joao", name: "João Raphael" },
    ],
  }),
}));

vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children, ...p }: any) => <span {...p}>{children}</span>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "data-testid": dt }: any) => (
    <button onClick={onClick} disabled={disabled} data-testid={dt}>
      {children}
    </button>
  ),
}));
vi.mock("./adsShared", () => ({
  AdsLoading: ({ label }: any) => <div data-testid="leadgen-loading">{label}</div>,
  AdsError: ({ message, onRetry }: any) => (
    <div data-testid="leadgen-error">
      {message}
      {onRetry && (
        <button data-testid="leadgen-error-retry" onClick={onRetry}>
          Tentar de novo
        </button>
      )}
    </div>
  ),
}));
vi.mock("lucide-react", () => ({
  Check: () => null,
  Copy: () => null,
  Info: () => null,
  Loader2: () => null,
  ShieldAlert: () => null,
  Webhook: () => null,
}));

function makeSubscriptions(overrides: Partial<any> = {}) {
  return {
    pages: [
      { page_id: "p1", page_name: "Loja Central", subscribed: true, subscribed_fields: ["leadgen"], app_id: "a1" },
      { page_id: "p2", page_name: "Loja Norte", subscribed: false, subscribed_fields: [], app_id: null },
    ],
    callback_url: "https://social.noctusai.com/api/meta/leadgen/webhook",
    verify_token_configured: true,
    gated: false,
    reason: null,
    ...overrides,
  };
}

function setDefaults() {
  mockUseLeadgenSubscriptions.mockReturnValue({
    data: makeSubscriptions(),
    isPending: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  });
  mockUseSubscribeLeadgenPages.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false, error: null });
  mockUseUnsubscribeLeadgenPage.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockUseSetPageClient.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockUseLeadgenEvents.mockReturnValue({
    data: { counts: { received: 5, processed: 4, error: 1 }, last_received_at: "2026-08-01T12:00:00Z", events: [] },
    isPending: false,
    isFetching: false,
    isError: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  setDefaults();
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn() },
    configurable: true,
  });
});

async function renderCard() {
  const React = (await import("react")).default;
  const { default: LeadgenWebhookCard } = await import("./LeadgenWebhookCard");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(LeadgenWebhookCard)), fireEvent: rtl.fireEvent };
}

describe("LeadgenWebhookCard — loading / error", () => {
  it("renders the loading state", async () => {
    mockUseLeadgenSubscriptions.mockReturnValue({ data: undefined, isPending: true, isFetching: false, isError: false, refetch: vi.fn() });
    const { getByTestId } = await renderCard();
    expect(getByTestId("leadgen-loading")).toBeTruthy();
  });

  it("renders the loading state while a background refetch is in flight (isPending false, isFetching true)", async () => {
    mockUseLeadgenSubscriptions.mockReturnValue({ data: makeSubscriptions(), isPending: false, isFetching: true, isError: false, refetch: vi.fn() });
    const { getByTestId } = await renderCard();
    expect(getByTestId("leadgen-loading")).toBeTruthy();
  });

  it("renders the error state and retries on click", async () => {
    const refetch = vi.fn();
    mockUseLeadgenSubscriptions.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true, refetch });
    const { getByTestId, fireEvent } = await renderCard();
    expect(getByTestId("leadgen-error")).toBeTruthy();
    fireEvent.click(getByTestId("leadgen-error-retry"));
    expect(refetch).toHaveBeenCalled();
  });
});

describe("LeadgenWebhookCard — gated / not-configured banners", () => {
  it("shows the gated banner with the server-provided reason", async () => {
    mockUseLeadgenSubscriptions.mockReturnValue({
      data: makeSubscriptions({ gated: true, reason: "Token sem permissão pages_manage_metadata." }),
      isPending: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    });
    const { getByTestId, getByText } = await renderCard();
    expect(getByTestId("leadgen-gated-banner")).toBeTruthy();
    expect(getByText("Token sem permissão pages_manage_metadata.")).toBeTruthy();
  });

  it("shows the not-configured banner when verify_token_configured is false", async () => {
    mockUseLeadgenSubscriptions.mockReturnValue({
      data: makeSubscriptions({ verify_token_configured: false }),
      isPending: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderCard();
    expect(getByTestId("leadgen-not-configured-banner")).toBeTruthy();
  });

  it("still shows the callback URL + copy button when not configured", async () => {
    mockUseLeadgenSubscriptions.mockReturnValue({
      data: makeSubscriptions({ verify_token_configured: false }),
      isPending: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    });
    const { getByText, getByTestId } = await renderCard();
    expect(getByText("https://social.noctusai.com/api/meta/leadgen/webhook")).toBeTruthy();
    expect(getByTestId("leadgen-copy-callback-url")).toBeTruthy();
  });

  it("omits both banners when configured and ungated", async () => {
    const { queryByTestId } = await renderCard();
    expect(queryByTestId("leadgen-gated-banner")).toBeNull();
    expect(queryByTestId("leadgen-not-configured-banner")).toBeNull();
  });
});

describe("LeadgenWebhookCard — callback URL copy", () => {
  it("copies the callback URL to the clipboard on click", async () => {
    const { getByTestId, fireEvent } = await renderCard();
    fireEvent.click(getByTestId("leadgen-copy-callback-url"));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      "https://social.noctusai.com/api/meta/leadgen/webhook",
    );
  });
});

describe("LeadgenWebhookCard — pages", () => {
  it("renders the empty state when there are no connected Pages", async () => {
    mockUseLeadgenSubscriptions.mockReturnValue({
      data: makeSubscriptions({ pages: [] }),
      isPending: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    });
    const { getByTestId, queryByTestId } = await renderCard();
    expect(getByTestId("leadgen-pages-empty")).toBeTruthy();
    expect(queryByTestId("leadgen-subscribe-all-btn")).toBeNull();
  });

  it("renders a subscribed and an unsubscribed row with the right badge + button label", async () => {
    const { getByTestId, getByText } = await renderCard();
    const row1 = getByTestId("leadgen-page-row-p1");
    const row2 = getByTestId("leadgen-page-row-p2");
    expect(row1.textContent).toContain("Loja Central");
    expect(row1.textContent).toContain("Inscrita");
    expect(row1.textContent).toContain("Desinscrever");
    expect(row2.textContent).toContain("Loja Norte");
    expect(row2.textContent).toContain("Não inscrita");
    expect(row2.textContent).toContain("Inscrever");
  });

  it("calls unsubscribe for a subscribed row and subscribe for an unsubscribed row", async () => {
    const unsubscribeMutate = vi.fn();
    const subscribeMutate = vi.fn();
    mockUseUnsubscribeLeadgenPage.mockReturnValue({ mutate: unsubscribeMutate, isPending: false });
    mockUseSubscribeLeadgenPages.mockReturnValue({ mutate: subscribeMutate, isPending: false, isError: false, error: null });
    const { getByTestId, fireEvent } = await renderCard();

    fireEvent.click(getByTestId("leadgen-page-row-p1").querySelector("button")!);
    expect(unsubscribeMutate).toHaveBeenCalledWith("p1", expect.any(Object));

    fireEvent.click(getByTestId("leadgen-page-row-p2").querySelector("button")!);
    expect(subscribeMutate).toHaveBeenCalledWith(["p2"], expect.any(Object));
  });
});

describe("LeadgenWebhookCard — bulk subscribe", () => {
  it("subscribes all pages with page_ids: null", async () => {
    const mutate = vi.fn();
    mockUseSubscribeLeadgenPages.mockReturnValue({ mutate, isPending: false, isError: false, error: null });
    const { getByTestId, fireEvent } = await renderCard();
    fireEvent.click(getByTestId("leadgen-subscribe-all-btn"));
    expect(mutate).toHaveBeenCalledWith(null, expect.any(Object));
  });

  it("renders a PARTIAL result — never collapsed to a blanket success or error", async () => {
    const mutate = vi.fn((_vars, opts) => {
      opts.onSuccess({
        results: [
          { page_id: "p1", ok: true, error: null },
          { page_id: "p2", ok: false, error: "Permissão insuficiente." },
        ],
      });
    });
    mockUseSubscribeLeadgenPages.mockReturnValue({ mutate, isPending: false, isError: false, error: null });
    const { getByTestId, fireEvent } = await renderCard();
    fireEvent.click(getByTestId("leadgen-subscribe-all-btn"));
    const summary = getByTestId("leadgen-bulk-results");
    expect(summary.textContent).toContain("1 de 2 página(s) inscrita(s).");
    expect(summary.textContent).toContain("Loja Norte:");
    expect(summary.textContent).toContain("Permissão insuficiente.");
  });
});

describe("LeadgenWebhookCard — delivery health", () => {
  it("renders the diagnostic message when last_received_at is null (never a bare zero)", async () => {
    mockUseLeadgenEvents.mockReturnValue({
      data: { counts: {}, last_received_at: null, events: [] },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId, queryByText } = await renderCard();
    expect(getByTestId("leadgen-never-received")).toBeTruthy();
    expect(queryByText(/^0$/)).toBeNull();
  });

  it("renders the last-received timestamp when events have arrived", async () => {
    const { getByTestId, queryByTestId } = await renderCard();
    expect(queryByTestId("leadgen-never-received")).toBeNull();
    expect(getByTestId("leadgen-delivery-health").textContent).toContain("Último evento recebido");
  });

  it("shows its own loading state without blocking the rest of the card", async () => {
    mockUseLeadgenEvents.mockReturnValue({ data: undefined, isPending: true, isFetching: false, isError: false });
    const { getByTestId } = await renderCard();
    expect(getByTestId("leadgen-health-loading")).toBeTruthy();
    // the subscription controls above/below it still render
    expect(getByTestId("leadgen-page-row-p1")).toBeTruthy();
  });

  it("shows its own error state without blocking the rest of the card", async () => {
    mockUseLeadgenEvents.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    const { getByTestId } = await renderCard();
    expect(getByTestId("leadgen-health-error")).toBeTruthy();
    expect(getByTestId("leadgen-page-row-p1")).toBeTruthy();
  });
});

// ─── Per-Page client attribution (migration 045) ────────────────────────────
// This is the key that decides WHICH client's recipients get a lead's PII.
// Unattributed is a legitimate state (alerts go to the org-wide tier), so the
// UI must state it rather than imply routing that is not happening.

describe("LeadgenWebhookCard — client attribution", () => {
  it("shows the attributed client, and 'no client' when unattributed", async () => {
    mockUseLeadgenSubscriptions.mockReturnValue({
      data: makeSubscriptions({
        pages: [
          { page_id: "p1", page_name: "Loja Central", subscribed: true,
            subscribed_fields: ["leadgen"], app_id: "a1",
            client_id: "client-one", forms_total: 3, forms_attributed: 3 },
          { page_id: "p2", page_name: "Loja Norte", subscribed: false,
            subscribed_fields: [], app_id: null,
            client_id: null, forms_total: 2, forms_attributed: 0 },
        ],
      }),
      isPending: false, isFetching: false, isError: false, refetch: vi.fn(),
    });
    const { getByLabelText } = await renderCard();

    expect((getByLabelText("Cliente da página Loja Central") as HTMLSelectElement).value)
      .toBe("client-one");
    expect((getByLabelText("Cliente da página Loja Norte") as HTMLSelectElement).value)
      .toBe("__none__");
  });

  it("attributes a Page to a client", async () => {
    const mutate = vi.fn();
    mockUseSetPageClient.mockReturnValue({ mutate, isPending: false });
    const { getByLabelText, fireEvent } = await renderCard();

    fireEvent.change(getByLabelText("Cliente da página Loja Central"), {
      target: { value: "client-joao" },
    });
    expect(mutate).toHaveBeenCalledWith(
      { pageId: "p1", clientId: "client-joao" },
      expect.anything(),
    );
  });

  it("clears an attribution with null, not the sentinel string", async () => {
    const mutate = vi.fn();
    mockUseSetPageClient.mockReturnValue({ mutate, isPending: false });
    mockUseLeadgenSubscriptions.mockReturnValue({
      data: makeSubscriptions({
        pages: [{ page_id: "p1", page_name: "Loja Central", subscribed: true,
                  subscribed_fields: ["leadgen"], app_id: "a1",
                  client_id: "client-one", forms_total: 1, forms_attributed: 1 }],
      }),
      isPending: false, isFetching: false, isError: false, refetch: vi.fn(),
    });
    const { getByLabelText, fireEvent } = await renderCard();

    fireEvent.change(getByLabelText("Cliente da página Loja Central"), {
      target: { value: "__none__" },
    });
    // 🔴 null, never "__none__": the sentinel is a DOM affordance and must not
    // reach the API, where it would be stored as a bogus client id.
    expect(mutate).toHaveBeenCalledWith(
      { pageId: "p1", clientId: null },
      expect.anything(),
    );
  });

  it("warns when a Page's forms are only PARTLY attributed", async () => {
    // A form that synced after the assignment carries NULL and still routes to
    // the org tier. Showing only the majority client would hide that entirely.
    mockUseLeadgenSubscriptions.mockReturnValue({
      data: makeSubscriptions({
        pages: [{ page_id: "p1", page_name: "Loja Central", subscribed: true,
                  subscribed_fields: ["leadgen"], app_id: "a1",
                  client_id: "client-one", forms_total: 5, forms_attributed: 3 }],
      }),
      isPending: false, isFetching: false, isError: false, refetch: vi.fn(),
    });
    const { getByText } = await renderCard();
    expect(getByText(/3\/5 formulários atribuídos/)).toBeTruthy();
  });

  it("does not warn when every form is attributed", async () => {
    mockUseLeadgenSubscriptions.mockReturnValue({
      data: makeSubscriptions({
        pages: [{ page_id: "p1", page_name: "Loja Central", subscribed: true,
                  subscribed_fields: ["leadgen"], app_id: "a1",
                  client_id: "client-one", forms_total: 4, forms_attributed: 4 }],
      }),
      isPending: false, isFetching: false, isError: false, refetch: vi.fn(),
    });
    const { queryByText } = await renderCard();
    expect(queryByText(/formulários atribuídos/)).toBeNull();
  });
});

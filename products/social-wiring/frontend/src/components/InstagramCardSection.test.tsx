/**
 * InstagramCardSection tests — the FE half of ig-login S2/S4.
 *
 * These pin the things that were actually broken or absent before this
 * component existed: there was no way to start Instagram OAuth from the UI at
 * all, and `useSubmitInstagramToken` had zero consumers. So the assertions here
 * are about WIRING (does the button reach the hook, with the right client) as
 * much as rendering.
 *
 * Mock strategy mirrors Conexoes.test.tsx: one hoisted vi.mock per module,
 * @noctusai/lib stubbed to avoid the dual-React render gap.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockAccounts = vi.fn();
const mockStartProviderOAuth = vi.fn();
const mockSubmitToken = vi.fn();
const mockDeleteAccount = vi.fn();
const mockSetDefaultAccount = vi.fn();

vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useIntegrationAccounts: mockAccounts,
  useStartProviderOAuth: mockStartProviderOAuth,
  useSubmitInstagramToken: mockSubmitToken,
  useDeleteAccount: mockDeleteAccount,
  useSetDefaultAccount: mockSetDefaultAccount,
}));

vi.mock("@noctusai/lib", () => ({
  IntegrationCard: ({ account }: any) => (
    <div data-testid="ig-card" data-account-id={account?.id}>
      {account?.account_label}
    </div>
  ),
  IntegrationCardModal: ({ account }: any) =>
    account ? <div data-testid="ig-modal" /> : null,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} {...rest}>
      {children}
    </button>
  ),
}));
vi.mock("@/components/ui/input", () => ({
  Input: (props: any) => <input {...props} />,
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const startMutate = vi.fn();
const submitMutate = vi.fn();

const igAccount = {
  id: "ig-1",
  org_id: "org-1",
  provider: "instagram",
  account_label: "@cliente",
  client_id: null,
  status: "validated",
  channel_info: { channel_id: "17841400000000000", title: "cliente" },
  metadata: { model: "instagram_login" },
  is_default: false,
  last_synced_at: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const idle = {
  data: [],
  isPending: false,
  isFetching: false,
  isError: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockAccounts.mockReturnValue(idle);
  mockStartProviderOAuth.mockReturnValue({
    mutate: startMutate,
    isPending: false,
  });
  mockSubmitToken.mockReturnValue({ mutate: submitMutate, isPending: false });
  mockDeleteAccount.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockSetDefaultAccount.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  });
});

async function render(clients: any[] = []) {
  const { InstagramCardSection } = await import("./InstagramCardSection");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(InstagramCardSection, { clients })),
    fireEvent: rtl.fireEvent,
  };
}

describe("InstagramCardSection — provider identity", () => {
  it("queries the instagram provider, not meta", async () => {
    await render();
    expect(mockAccounts).toHaveBeenCalledWith("instagram");
    // 🔴 Crossing meta/instagram credential families is the documented live
    // failure; the section must never reach for the Facebook-Login provider.
    expect(mockAccounts).not.toHaveBeenCalledWith("meta");
  });

  it("binds the OAuth-start hook to the instagram provider", async () => {
    await render();
    expect(mockStartProviderOAuth).toHaveBeenCalledWith("instagram");
  });
});

describe("InstagramCardSection — connect", () => {
  it("starts OAuth with no client when none is selected", async () => {
    const { getByText, fireEvent } = await render();
    fireEvent.click(getByText("Conectar Instagram"));
    expect(startMutate).toHaveBeenCalledTimes(1);
    expect(startMutate.mock.calls[0][0]).toBeUndefined();
  });

  it("passes the selected client through to OAuth start", async () => {
    const clients = [{ id: "client-a", name: "Acme" }];
    const { getByText, getByLabelText, fireEvent } = await render(clients);
    fireEvent.change(getByLabelText("Atribuir a cliente ao conectar"), {
      target: { value: "client-a" },
    });
    fireEvent.click(getByText("Conectar Instagram"));
    expect(startMutate.mock.calls[0][0]).toEqual({ clientId: "client-a" });
  });
});

describe("InstagramCardSection — manual token fallback", () => {
  it("is collapsed until requested", async () => {
    const { queryByLabelText } = await render();
    expect(queryByLabelText("Instagram User access token")).toBeNull();
  });

  it("submits a pasted token", async () => {
    const { getByText, getByLabelText, fireEvent } = await render();
    fireEvent.click(getByText("Colar token"));
    fireEvent.change(getByLabelText("Instagram User access token"), {
      target: { value: "  IGQ-real-token  " },
    });
    fireEvent.click(getByText("Salvar"));
    expect(submitMutate).toHaveBeenCalledTimes(1);
    // Trimmed — a copy-paste with stray whitespace must not be stored verbatim.
    expect(submitMutate.mock.calls[0][0]).toMatchObject({
      access_token: "IGQ-real-token",
    });
  });

  it("does not submit an empty or whitespace-only token", async () => {
    const { getByText, getByLabelText, fireEvent } = await render();
    fireEvent.click(getByText("Colar token"));
    fireEvent.change(getByLabelText("Instagram User access token"), {
      target: { value: "   " },
    });
    fireEvent.click(getByText("Salvar"));
    expect(submitMutate).not.toHaveBeenCalled();
  });

  it("renders the token field as a password input", async () => {
    const { getByText, getByLabelText, fireEvent } = await render();
    fireEvent.click(getByText("Colar token"));
    // A user access token is a live credential — it must not be shoulder-readable.
    expect(getByLabelText("Instagram User access token")).toHaveProperty(
      "type",
      "password",
    );
  });
});

describe("InstagramCardSection — states", () => {
  it("shows a loading cue during a background refetch, not the empty state", async () => {
    // The lying-loading-state class: isFetching true with isPending false is
    // exactly the frame where `isLoading` would be FALSE and an isEmpty branch
    // would render "nenhuma conta" over accounts that exist.
    mockAccounts.mockReturnValue({ ...idle, isFetching: true, data: [igAccount] });
    const { getByText, queryByText } = await render();
    expect(getByText(/Carregando contas do Instagram/)).toBeTruthy();
    expect(queryByText(/Nenhuma conta do Instagram conectada/)).toBeNull();
  });

  it("shows the empty state only when genuinely settled and empty", async () => {
    const { getByText } = await render();
    expect(getByText(/Nenhuma conta do Instagram conectada/)).toBeTruthy();
  });

  it("renders a card per connected account", async () => {
    mockAccounts.mockReturnValue({ ...idle, data: [igAccount] });
    const { getAllByTestId } = await render();
    expect(getAllByTestId("ig-card")).toHaveLength(1);
  });

  it("shows an error state when the query fails", async () => {
    mockAccounts.mockReturnValue({ ...idle, isError: true });
    const { getByText } = await render();
    expect(getByText(/Erro ao carregar contas/)).toBeTruthy();
  });
});

/**
 * EmailMarketingConfig.test.tsx — unit tests for the Mailchimp config page.
 *
 * Covers:
 *   1. Disconnected state renders API key form.
 *   2. Connect submit disabled when key is empty.
 *   3. Connect submit enabled when key is filled.
 *   4. Error message renders on invalid key error.
 *   5. Connected state renders audience selector + action buttons.
 *   6. Disconnect button opens confirm dialog.
 *   7. Confirm disconnect calls remove mutation.
 *   8. Replace key button transitions back to key form.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseMailchimpConnection = vi.fn();
const mockUseMailchimpAudiences = vi.fn();
const mockUseMailchimpConnectionMutations = vi.fn();

vi.mock("@/hooks/useMailchimpConnection", () => ({
  useMailchimpConnection: mockUseMailchimpConnection,
  useMailchimpAudiences: mockUseMailchimpAudiences,
  useMailchimpConnectionMutations: mockUseMailchimpConnectionMutations,
}));

// ─── UI stubs ────────────────────────────────────────────────────────────────

vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: any) => <div data-testid="skeleton" className={className} />,
}));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: any) => <span>{children}</span>,
}));
vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...props }: any) => <div {...props}>{children}</div>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "data-testid": dt, variant, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} data-testid={dt} {...rest}>
      {children}
    </button>
  ),
}));
vi.mock("@/components/ui/input", () => ({
  Input: ({ onChange, value, disabled, "data-testid": dt, type, placeholder, ...rest }: any) => (
    <input
      type={type ?? "text"}
      value={value ?? ""}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      data-testid={dt}
      {...rest}
    />
  ),
}));
vi.mock("@/components/ui/label", () => ({
  Label: ({ children, htmlFor }: any) => <label htmlFor={htmlFor}>{children}</label>,
}));
vi.mock("@/components/ui/select", () => ({
  Select: ({ children, onValueChange }: any) => <div>{children}</div>,
  SelectTrigger: ({ children, "data-testid": dt }: any) => <div data-testid={dt}>{children}</div>,
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children, value }: any) => (
    <div data-value={value}>{children}</div>
  ),
}));
vi.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children, open }: any) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogContent: ({ children }: any) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: any) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: any) => <h3>{children}</h3>,
  AlertDialogDescription: ({ children }: any) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick, "data-testid": dt }: any) => (
    <button onClick={onClick} data-testid={dt}>{children}</button>
  ),
  AlertDialogCancel: ({ children }: any) => <button>{children}</button>,
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// ─── Fixtures ────────────────────────────────────────────────────────────────

const makeAudience = () => ({
  id: "list-1",
  name: "Minha Lista",
  member_count: 100,
  unsubscribe_count: 5,
});

const defaultMutations = () => ({
  put: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  },
  patch: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  },
  remove: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  },
});

beforeEach(() => {
  mockUseMailchimpConnection.mockReturnValue({
    data: { connected: false },
    isLoading: false,
  });
  mockUseMailchimpAudiences.mockReturnValue({
    data: null,
    isLoading: false,
  });
  mockUseMailchimpConnectionMutations.mockReturnValue(defaultMutations());
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function renderConfig() {
  const React = (await import("react")).default;
  const { default: EmailMarketingConfig } = await import("./EmailMarketingConfig");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(EmailMarketingConfig)), fireEvent: rtl.fireEvent };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("EmailMarketingConfig — disconnected state", () => {
  it("renders API key form when not connected", async () => {
    const { getByTestId } = await renderConfig();
    expect(getByTestId("mailchimp-config-form")).toBeTruthy();
    expect(getByTestId("mailchimp-api-key-input")).toBeTruthy();
  });

  it("connect submit disabled when key is empty", async () => {
    const { getByTestId } = await renderConfig();
    const btn = getByTestId("mailchimp-connect-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("connect submit enabled when key is filled", async () => {
    const { getByTestId, fireEvent } = await renderConfig();
    fireEvent.change(getByTestId("mailchimp-api-key-input") as HTMLInputElement, {
      target: { value: "abc123-us6" },
    });
    const btn = getByTestId("mailchimp-connect-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("renders error message when connect submit fails with onError callback", async () => {
    // The component uses local putError state set in mutate({}, { onError }) callback.
    // Simulate by making mutate immediately call onError.
    const errorMutations = defaultMutations();
    errorMutations.put.mutate = vi.fn().mockImplementation((_body: any, opts: any) => {
      opts?.onError?.({
        body: { detail: { message: "Chave inválida" } },
      });
    });
    mockUseMailchimpConnectionMutations.mockReturnValue(errorMutations);
    const { container, getByTestId, fireEvent } = await renderConfig();
    fireEvent.change(getByTestId("mailchimp-api-key-input") as HTMLInputElement, {
      target: { value: "badkey-us6" },
    });
    // Fire submit on the actual form element
    const form = container.querySelector("form") as HTMLFormElement;
    fireEvent.submit(form);
    expect(getByTestId("mailchimp-connect-error")).toBeTruthy();
  });
});

describe("EmailMarketingConfig — connected state", () => {
  beforeEach(() => {
    mockUseMailchimpConnection.mockReturnValue({
      data: {
        connected: true,
        datacenter: "us6",
        audience_id: "list-1",
        account_name: "Minha Conta",
        email: "joao@exemplo.com",
      },
      isLoading: false,
    });
    mockUseMailchimpAudiences.mockReturnValue({
      data: { items: [makeAudience()], total: 1 },
      isLoading: false,
    });
  });

  it("renders connected state with audience selector", async () => {
    const { getByTestId } = await renderConfig();
    expect(getByTestId("mailchimp-connected-state")).toBeTruthy();
    expect(getByTestId("mailchimp-audience-select")).toBeTruthy();
  });

  it("renders replace key and disconnect buttons", async () => {
    const { getByTestId } = await renderConfig();
    expect(getByTestId("mailchimp-replace-key-btn")).toBeTruthy();
    expect(getByTestId("mailchimp-disconnect-btn")).toBeTruthy();
  });

  it("disconnect button opens confirm dialog", async () => {
    const { getByTestId, fireEvent } = await renderConfig();
    fireEvent.click(getByTestId("mailchimp-disconnect-btn"));
    expect(getByTestId("mailchimp-confirm-disconnect")).toBeTruthy();
  });

  it("confirm disconnect calls remove mutation", async () => {
    const removeMutate = vi.fn();
    mockUseMailchimpConnectionMutations.mockReturnValue({
      ...defaultMutations(),
      remove: { mutate: removeMutate, isPending: false, isError: false, error: null },
    });
    const { getByTestId, fireEvent } = await renderConfig();
    fireEvent.click(getByTestId("mailchimp-disconnect-btn"));
    fireEvent.click(getByTestId("mailchimp-confirm-disconnect"));
    expect(removeMutate).toHaveBeenCalled();
  });

  it("replace key button reverts to form state", async () => {
    const { getByTestId, fireEvent } = await renderConfig();
    fireEvent.click(getByTestId("mailchimp-replace-key-btn"));
    expect(getByTestId("mailchimp-api-key-input")).toBeTruthy();
  });
});

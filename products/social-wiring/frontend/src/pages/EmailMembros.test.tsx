/**
 * EmailMembros.test.tsx — unit tests for the Mailchimp audience member page.
 *
 * EmailMembros is READ-THROUGH: it fetches from Mailchimp via our proxy API
 * and NEVER writes to social_wiring.contacts. It is wrapped in MailchimpGate.
 *
 * Covers:
 *   1. Gate renders NotConnected when disconnected.
 *   2. Gate renders loading state while probe is in flight.
 *   3. Loading state renders skeleton.
 *   4. Empty state renders when no members.
 *   5. Error state renders on failure.
 *   6. Member rows render with email.
 *   7. Adicionar membro button opens modal.
 *   8. Modal submit disabled when email is empty.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseMailchimpConnection = vi.fn();
const mockUseMailchimpContacts = vi.fn();
const mockUseMailchimpContactMutations = vi.fn();

vi.mock("@/hooks/useMailchimpConnection", () => ({
  useMailchimpConnection: mockUseMailchimpConnection,
  useMailchimpAudiences: vi.fn(() => ({ data: null })),
  useMailchimpConnectionMutations: vi.fn(() => ({
    put: { mutate: vi.fn(), isPending: false },
    patch: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
  })),
}));

vi.mock("@/hooks/useMailchimpContacts", () => ({
  useMailchimpContacts: mockUseMailchimpContacts,
  useMailchimpContact: vi.fn(() => ({ data: null })),
  useMailchimpContactMutations: mockUseMailchimpContactMutations,
}));

// ─── UI stubs ────────────────────────────────────────────────────────────────

vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: any) => (
    <div data-testid="skeleton" className={className} />
  ),
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
  Button: ({ children, onClick, disabled, "data-testid": dt, ...rest }: any) => (
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
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: any) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
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
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: any) => <div>{children}</div>,
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("react-router-dom", () => ({
  Link: ({ children, to }: any) => <a href={to}>{children}</a>,
  useNavigate: () => vi.fn(),
}));
vi.mock("date-fns", () => ({
  format: () => "01/06/2026",
}));
vi.mock("date-fns/locale", () => ({
  ptBR: {},
}));

// ─── Fixtures ────────────────────────────────────────────────────────────────

const makeMember = (email = "joao@exemplo.com") => ({
  email,
  status: "subscribed",
  first_name: "João",
  last_name: "Silva",
  tags: ["vip"],
  vip: true,
  last_changed: "2026-06-01T10:00:00Z",
});

const defaultMutations = () => ({
  upsert: { mutate: vi.fn(), isPending: false },
  archive: { mutate: vi.fn(), isPending: false },
});

beforeEach(() => {
  mockUseMailchimpConnection.mockReturnValue({
    data: { connected: true },
    isPending: false,
  });
  mockUseMailchimpContacts.mockReturnValue({
    data: { items: [], total: 0 },
    isLoading: false,
    isError: false,
    error: null,
  });
  mockUseMailchimpContactMutations.mockReturnValue(defaultMutations());
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function renderEmailMembros() {
  const React = (await import("react")).default;
  const { default: EmailMembros } = await import("./EmailMembros");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(EmailMembros)), fireEvent: rtl.fireEvent };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("EmailMembros — MailchimpGate", () => {
  it("shows NotConnected when connection.connected=false", async () => {
    mockUseMailchimpConnection.mockReturnValue({
      data: { connected: false },
      isPending: false,
    });
    const { getByTestId } = await renderEmailMembros();
    expect(getByTestId("mailchimp-not-connected")).toBeTruthy();
  });

  it("shows loading skeleton while gate probe is in flight", async () => {
    mockUseMailchimpConnection.mockReturnValue({
      data: undefined,
      isPending: true,
    });
    const { getByTestId } = await renderEmailMembros();
    expect(getByTestId("mailchimp-gate-loading")).toBeTruthy();
  });
});

describe("EmailMembros — loading / empty / error / success states", () => {
  it("renders loading skeleton while members are fetching", async () => {
    mockUseMailchimpContacts.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    const { getByTestId } = await renderEmailMembros();
    expect(getByTestId("membros-loading")).toBeTruthy();
  });

  it("renders empty state when no members", async () => {
    const { getByTestId } = await renderEmailMembros();
    expect(getByTestId("membros-empty")).toBeTruthy();
  });

  it("renders error card on failure", async () => {
    mockUseMailchimpContacts.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Network Error"),
    });
    const { getByTestId } = await renderEmailMembros();
    expect(getByTestId("membros-error")).toBeTruthy();
  });

  it("renders member rows with email", async () => {
    mockUseMailchimpContacts.mockReturnValue({
      data: { items: [makeMember()], total: 1 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderEmailMembros();
    expect(getByTestId("membro-row-joao@exemplo.com")).toBeTruthy();
  });
});

describe("EmailMembros — modal", () => {
  it("Adicionar membro button opens modal", async () => {
    const { getByTestId, fireEvent } = await renderEmailMembros();
    fireEvent.click(getByTestId("btn-novo-membro"));
    expect(getByTestId("dialog")).toBeTruthy();
  });

  it("submit disabled when email is empty in create mode", async () => {
    const { getByTestId, fireEvent } = await renderEmailMembros();
    fireEvent.click(getByTestId("btn-novo-membro"));
    const btn = getByTestId("membro-modal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit enabled when email is filled in create mode", async () => {
    const { getByTestId, fireEvent } = await renderEmailMembros();
    fireEvent.click(getByTestId("btn-novo-membro"));
    fireEvent.change(getByTestId("membro-email-input") as HTMLInputElement, {
      target: { value: "novo@exemplo.com" },
    });
    const btn = getByTestId("membro-modal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });
});

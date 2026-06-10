/**
 * Contatos.test.tsx — unit tests for the Mailchimp contacts page.
 *
 * Covers:
 *   1. Gate renders NotConnected when connection.connected=false.
 *   2. Gate renders children when connection.connected=true.
 *   3. Loading state renders skeleton.
 *   4. Empty state renders when no contacts.
 *   5. Contact rows render email and status.
 *   6. Novo contato button opens upsert modal.
 *   7. Modal submit is disabled when email is empty (create mode).
 *   8. Archive button triggers archive mutation.
 *
 * Mock strategy: one vi.mock per module (hoisted). All hooks configured per-test.
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
  Button: ({ children, onClick, disabled, "data-testid": dt, asChild, ...rest }: any) => (
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
  Select: ({ children, onValueChange }: any) => <div>{children}</div>,
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
    isLoading: false,
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

async function renderContatos() {
  const React = (await import("react")).default;
  const { default: Contatos } = await import("./Contatos");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Contatos)), fireEvent: rtl.fireEvent };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("Contatos — MailchimpGate", () => {
  it("shows NotConnected when connection.connected=false", async () => {
    mockUseMailchimpConnection.mockReturnValue({
      data: { connected: false },
      isLoading: false,
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("mailchimp-not-connected")).toBeTruthy();
  });

  it("shows loading skeleton while gate probe is in flight", async () => {
    mockUseMailchimpConnection.mockReturnValue({
      data: undefined,
      isLoading: true,
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("mailchimp-gate-loading")).toBeTruthy();
  });
});

describe("Contatos — loading / empty / error / success states", () => {
  it("renders loading skeleton while contacts are fetching", async () => {
    mockUseMailchimpContacts.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("contatos-loading")).toBeTruthy();
  });

  it("renders empty state when no contacts", async () => {
    const { getByTestId } = await renderContatos();
    expect(getByTestId("contatos-empty")).toBeTruthy();
  });

  it("renders contact rows when data present", async () => {
    mockUseMailchimpContacts.mockReturnValue({
      data: { items: [makeMember()], total: 1 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("contato-row-joao@exemplo.com")).toBeTruthy();
  });

  it("renders error card on failure", async () => {
    mockUseMailchimpContacts.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: { body: { detail: { message: "Erro de rede" } } },
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("contatos-error")).toBeTruthy();
  });
});

describe("Contatos — create modal", () => {
  it("Novo contato button opens modal", async () => {
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("btn-novo-contato"));
    expect(getByTestId("dialog")).toBeTruthy();
  });

  it("submit disabled when email is empty", async () => {
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("btn-novo-contato"));
    const btn = getByTestId("contact-modal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit enabled when email is filled", async () => {
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("btn-novo-contato"));
    fireEvent.change(getByTestId("contact-email-input") as HTMLInputElement, {
      target: { value: "novo@exemplo.com" },
    });
    const btn = getByTestId("contact-modal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });
});

describe("Contatos — archive", () => {
  it("archive button opens confirm dialog", async () => {
    mockUseMailchimpContacts.mockReturnValue({
      data: { items: [makeMember()], total: 1 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("archive-contato-joao@exemplo.com"));
    expect(getByTestId("alert-dialog")).toBeTruthy();
  });

  it("confirm archive calls archive mutation", async () => {
    const archiveMutate = vi.fn();
    mockUseMailchimpContactMutations.mockReturnValue({
      ...defaultMutations(),
      archive: { mutate: archiveMutate, isPending: false },
    });
    mockUseMailchimpContacts.mockReturnValue({
      data: { items: [makeMember()], total: 1 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("archive-contato-joao@exemplo.com"));
    fireEvent.click(getByTestId("confirm-archive-contato"));
    expect(archiveMutate).toHaveBeenCalledWith(
      "joao@exemplo.com",
      expect.any(Object),
    );
  });
});

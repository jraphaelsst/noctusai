/**
 * Contatos.test.tsx — unit tests for the in-home platform contacts page.
 *
 * The Contatos page now shows LOCAL platform contacts (social_wiring.contacts)
 * NOT Mailchimp members. No MailchimpGate wrapping.
 *
 * Covers:
 *   1. Loading state renders skeleton.
 *   2. Empty state renders when no contacts.
 *   3. Error state renders on failure.
 *   4. Contact row renders nome as primary label + source badge.
 *   5. Novo contato button opens upsert modal.
 *   6. Modal submit disabled when email is empty (create mode).
 *   7. Modal submit enabled when email is filled.
 *   8. Archive button opens confirm dialog.
 *   9. Confirm archive calls archive mutation.
 *
 * Mock strategy: one vi.mock per module (hoisted). All hooks configured per-test.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseContacts = vi.fn();
const mockUseContactMutations = vi.fn();

vi.mock("@/hooks/useContacts", () => ({
  useContacts: mockUseContacts,
  useContactMutations: mockUseContactMutations,
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

// ─── Fixtures ────────────────────────────────────────────────────────────────

const makeContact = (overrides: Record<string, any> = {}) => ({
  id: "contact-1",
  org_id: "org-1",
  nome: "João Silva",
  email: "joao@exemplo.com",
  telefone: "+5511999998888",
  empresa: "Acme Ltda.",
  tags: ["vip"],
  source: "manual",
  status: "active",
  whatsapp_phone: null,
  whatsapp_lids: [],
  whatsapp_jid: null,
  created_at: "2026-06-01T10:00:00Z",
  updated_at: null,
  custom_fields: {},
  ...overrides,
});

const makeContactsPage = (contacts: any[] = []) => ({
  data: contacts,
  pagination: {
    page: 1,
    page_size: 20,
    total: contacts.length,
    total_pages: 1,
  },
});

const defaultMutations = () => ({
  create: { mutate: vi.fn(), isPending: false },
  update: { mutate: vi.fn(), isPending: false },
  archive: { mutate: vi.fn(), isPending: false },
});

beforeEach(() => {
  mockUseContacts.mockReturnValue({
    data: makeContactsPage([]),
    isPending: false,
      isFetching: false,
    isError: false,
    error: null,
  });
  mockUseContactMutations.mockReturnValue(defaultMutations());
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function renderContatos() {
  const React = (await import("react")).default;
  const { default: Contatos } = await import("./Contatos");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Contatos)), fireEvent: rtl.fireEvent };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("Contatos (in-home) — loading / empty / error / success states", () => {
  it("renders loading skeleton while contacts are fetching", async () => {
    mockUseContacts.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("contatos-loading")).toBeTruthy();
  });

  it("renders empty state when no contacts", async () => {
    const { getByTestId } = await renderContatos();
    expect(getByTestId("contatos-empty")).toBeTruthy();
  });

  it("renders error card on failure", async () => {
    mockUseContacts.mockReturnValue({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: true,
      error: new Error("Network Error"),
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("contatos-error")).toBeTruthy();
  });

  it("renders contact row with nome as primary label", async () => {
    mockUseContacts.mockReturnValue({
      data: makeContactsPage([makeContact()]),
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId, getByText } = await renderContatos();
    expect(getByTestId("contato-row-contact-1")).toBeTruthy();
    expect(getByText("João Silva")).toBeTruthy();
  });

  it("renders source badge for WhatsApp contacts", async () => {
    mockUseContacts.mockReturnValue({
      data: makeContactsPage([makeContact({ source: "whatsapp", id: "contact-2" })]),
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("source-badge-whatsapp")).toBeTruthy();
  });

  it("renders source badge for manual contacts", async () => {
    mockUseContacts.mockReturnValue({
      data: makeContactsPage([makeContact()]),
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await renderContatos();
    expect(getByTestId("source-badge-manual")).toBeTruthy();
  });

  it("does NOT render MailchimpGate (no mailchimp-not-connected testid)", async () => {
    const { queryByTestId } = await renderContatos();
    // The in-home page must never show the Mailchimp gate
    expect(queryByTestId("mailchimp-not-connected")).toBeNull();
    expect(queryByTestId("mailchimp-gate-loading")).toBeNull();
  });
});

describe("Contatos (in-home) — create modal", () => {
  it("Novo contato button opens modal", async () => {
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("btn-novo-contato"));
    expect(getByTestId("dialog")).toBeTruthy();
  });

  it("submit disabled when email is empty in create mode", async () => {
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("btn-novo-contato"));
    const btn = getByTestId("contact-modal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit enabled when email is filled in create mode", async () => {
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("btn-novo-contato"));
    fireEvent.change(getByTestId("contact-email-input") as HTMLInputElement, {
      target: { value: "novo@exemplo.com" },
    });
    const btn = getByTestId("contact-modal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });
});

describe("Contatos (in-home) — archive", () => {
  it("archive button opens confirm dialog", async () => {
    mockUseContacts.mockReturnValue({
      data: makeContactsPage([makeContact()]),
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("archive-contato-contact-1"));
    expect(getByTestId("alert-dialog")).toBeTruthy();
  });

  it("confirm archive calls archive mutation with contact id", async () => {
    const archiveMutate = vi.fn();
    mockUseContactMutations.mockReturnValue({
      ...defaultMutations(),
      archive: { mutate: archiveMutate, isPending: false },
    });
    mockUseContacts.mockReturnValue({
      data: makeContactsPage([makeContact()]),
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId, fireEvent } = await renderContatos();
    fireEvent.click(getByTestId("archive-contato-contact-1"));
    fireEvent.click(getByTestId("confirm-archive-contato"));
    expect(archiveMutate).toHaveBeenCalledWith("contact-1", expect.any(Object));
  });
});

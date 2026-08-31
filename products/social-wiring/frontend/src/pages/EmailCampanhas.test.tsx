/**
 * EmailCampanhas.test.tsx — unit tests for the Mailchimp campaigns page.
 *
 * Covers:
 *   1. Gate: NotConnected when disconnected.
 *   2. Loading state.
 *   3. Campaign rows render with title and status badges.
 *   4. Rascunho badge for draft campaigns.
 *   5. Enviada badge for sent campaigns.
 *   6. Nova campanha button opens create modal.
 *   7. Create modal submit disabled without required fields.
 *   8. Send confirm dialog opens and fires mutation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseMailchimpConnection = vi.fn();
const mockUseMailchimpCampaigns = vi.fn();
const mockUseMailchimpCampaignMutations = vi.fn();
const mockUseMailchimpSegments = vi.fn();
const mockUseMailchimpTemplates = vi.fn();

vi.mock("@/hooks/useMailchimpConnection", () => ({
  useMailchimpConnection: mockUseMailchimpConnection,
  useMailchimpAudiences: vi.fn(() => ({ data: null })),
  useMailchimpConnectionMutations: vi.fn(() => ({})),
}));

vi.mock("@/hooks/useMailchimpCampaigns", () => ({
  useMailchimpCampaigns: mockUseMailchimpCampaigns,
  useMailchimpCampaign: vi.fn(() => ({ data: null })),
  useMailchimpCampaignMutations: mockUseMailchimpCampaignMutations,
}));

vi.mock("@/hooks/useMailchimpSegments", () => ({
  useMailchimpSegments: mockUseMailchimpSegments,
  useMailchimpSegmentMembers: vi.fn(() => ({ data: null })),
  useMailchimpSegmentMutations: vi.fn(() => ({})),
}));

vi.mock("@/hooks/useMailchimpTemplates", () => ({
  useMailchimpTemplates: mockUseMailchimpTemplates,
  useMailchimpTemplate: vi.fn(() => ({ data: null })),
  useMailchimpTemplateMutations: vi.fn(() => ({})),
}));

// ─── UI stubs ────────────────────────────────────────────────────────────────

vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: any) => <div data-testid="skeleton" className={className} />,
}));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children, ...props }: any) => <span {...props}>{children}</span>,
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
  DialogContent: ({ children, "data-testid": dt, ...rest }: any) => (
    <div data-testid={dt} {...rest}>{children}</div>
  ),
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
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
vi.mock("date-fns", () => ({ format: () => "01/06/2026" }));
vi.mock("date-fns/locale", () => ({ ptBR: {} }));

// ─── Fixtures ────────────────────────────────────────────────────────────────

// CampaignOut shape (flat fields — per hook type definition)
const makeDraftCampaign = () => ({
  id: "camp-001",
  web_id: 1001,
  title: "Campanha Junho",
  status: "save" as const,
  subject_line: "Assunto Junho",
  preview_text: null,
  from_name: "Social Wiring",
  reply_to: "noreply@social.com",
  segment_id: null,
  template_id: null,
  send_time: null,
  create_time: "2026-06-01T10:00:00Z",
  emails_sent: 0,
  opens: null,
  clicks: null,
  archive_url: null,
});

const makeSentCampaign = () => ({
  id: "camp-002",
  web_id: 1002,
  title: "Newsletter Maio",
  status: "sent" as const,
  subject_line: "Assunto Maio",
  preview_text: null,
  from_name: "Social Wiring",
  reply_to: "noreply@social.com",
  segment_id: null,
  template_id: null,
  send_time: "2026-05-01T10:00:00Z",
  create_time: "2026-05-01T09:00:00Z",
  emails_sent: 500,
  opens: 100,
  clicks: 50,
  archive_url: "https://mailchi.mp/exemplo/newsletter-maio",
});

const defaultMutations = () => ({
  create: { mutate: vi.fn(), isPending: false },
  update: { mutate: vi.fn(), isPending: false },
  remove: { mutate: vi.fn(), isPending: false },
  send: { mutate: vi.fn(), isPending: false },
  schedule: { mutate: vi.fn(), isPending: false },
  unschedule: { mutate: vi.fn(), isPending: false },
  sendTest: { mutate: vi.fn(), isPending: false },
});

beforeEach(() => {
  mockUseMailchimpConnection.mockReturnValue({ data: { connected: true }, isPending: false });
  mockUseMailchimpCampaigns.mockReturnValue({
    data: { items: [], total: 0 },
    isLoading: false,
    isError: false,
    error: null,
  });
  mockUseMailchimpCampaignMutations.mockReturnValue(defaultMutations());
  mockUseMailchimpSegments.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false });
  mockUseMailchimpTemplates.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false });
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function renderCampanhas() {
  const React = (await import("react")).default;
  const { default: EmailCampanhas } = await import("./EmailCampanhas");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(EmailCampanhas)), fireEvent: rtl.fireEvent };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("EmailCampanhas — gate", () => {
  it("shows NotConnected when disconnected", async () => {
    mockUseMailchimpConnection.mockReturnValue({ data: { connected: false }, isPending: false });
    const { getByTestId } = await renderCampanhas();
    expect(getByTestId("mailchimp-not-connected")).toBeTruthy();
  });

  it("shows loading skeleton while gate probe is in flight", async () => {
    mockUseMailchimpConnection.mockReturnValue({ data: undefined, isPending: true });
    const { getByTestId } = await renderCampanhas();
    expect(getByTestId("mailchimp-gate-loading")).toBeTruthy();
  });
});

describe("EmailCampanhas — loading / empty / success states", () => {
  it("renders loading skeleton while campaigns are fetching", async () => {
    mockUseMailchimpCampaigns.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    const { getByTestId } = await renderCampanhas();
    expect(getByTestId("campanhas-loading")).toBeTruthy();
  });

  it("renders empty state when no campaigns", async () => {
    const { getByTestId } = await renderCampanhas();
    expect(getByTestId("campanhas-empty")).toBeTruthy();
  });

  it("renders campaign rows when data present", async () => {
    mockUseMailchimpCampaigns.mockReturnValue({
      data: { items: [makeDraftCampaign(), makeSentCampaign()], total: 2 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderCampanhas();
    expect(getByTestId("campanha-row-camp-001")).toBeTruthy();
    expect(getByTestId("campanha-row-camp-002")).toBeTruthy();
  });
});

describe("EmailCampanhas — status badges", () => {
  it("draft campaign shows 'Rascunho' badge", async () => {
    mockUseMailchimpCampaigns.mockReturnValue({
      data: { items: [makeDraftCampaign()], total: 1 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderCampanhas();
    const badge = getByTestId("status-badge-camp-001");
    expect(badge.textContent).toContain("Rascunho");
  });

  it("sent campaign shows 'Enviada' badge", async () => {
    mockUseMailchimpCampaigns.mockReturnValue({
      data: { items: [makeSentCampaign()], total: 1 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId } = await renderCampanhas();
    const badge = getByTestId("status-badge-camp-002");
    expect(badge.textContent).toContain("Enviada");
  });
});

describe("EmailCampanhas — create modal", () => {
  it("Nova campanha button opens create modal", async () => {
    const { getByTestId, fireEvent } = await renderCampanhas();
    fireEvent.click(getByTestId("btn-nova-campanha"));
    expect(getByTestId("create-campanha-modal")).toBeTruthy();
  });

  it("submit disabled without required fields", async () => {
    const { getByTestId, fireEvent } = await renderCampanhas();
    fireEvent.click(getByTestId("btn-nova-campanha"));
    const btn = getByTestId("create-campanha-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit enabled when required fields filled", async () => {
    const { getByTestId, fireEvent } = await renderCampanhas();
    fireEvent.click(getByTestId("btn-nova-campanha"));
    fireEvent.change(getByTestId("campanha-title-input") as HTMLInputElement, {
      target: { value: "Minha Campanha" },
    });
    fireEvent.change(getByTestId("campanha-subject-input") as HTMLInputElement, {
      target: { value: "Assunto" },
    });
    fireEvent.change(getByTestId("campanha-from-input") as HTMLInputElement, {
      target: { value: "Social Wiring" },
    });
    fireEvent.change(getByTestId("campanha-reply-input") as HTMLInputElement, {
      target: { value: "reply@social.com" },
    });
    const btn = getByTestId("create-campanha-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });
});

describe("EmailCampanhas — send action", () => {
  it("send button opens send confirm dialog", async () => {
    mockUseMailchimpCampaigns.mockReturnValue({
      data: { items: [makeDraftCampaign()], total: 1 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId, fireEvent } = await renderCampanhas();
    fireEvent.click(getByTestId("send-btn-camp-001"));
    expect(getByTestId("confirm-send-campanha")).toBeTruthy();
  });

  it("confirm send calls send mutation", async () => {
    const sendMutate = vi.fn();
    mockUseMailchimpCampaignMutations.mockReturnValue({
      ...defaultMutations(),
      send: { mutate: sendMutate, isPending: false },
    });
    mockUseMailchimpCampaigns.mockReturnValue({
      data: { items: [makeDraftCampaign()], total: 1 },
      isLoading: false,
      isError: false,
    });
    const { getByTestId, fireEvent } = await renderCampanhas();
    fireEvent.click(getByTestId("send-btn-camp-001"));
    fireEvent.click(getByTestId("confirm-send-campanha"));
    expect(sendMutate).toHaveBeenCalledWith("camp-001", expect.any(Object));
  });
});

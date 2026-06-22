/**
 * Conexao.tsx — unit tests for the WAHA connections UI.
 *
 * Covers:
 *   1. Create form has exactly 2 inputs (Nome + API key); no session/server/webhook.
 *   2. Create submit button disabled when either field is empty.
 *   3. Create submit button enabled when both fields filled.
 *   4. Create mutation payload is { label, api_key } — no extra fields.
 *   5. After successful create the create dialog closes and the detail/QR dialog
 *      opens with autoStart=true (detail dialog is rendered).
 *   6. Empty-state card renders when no connections.
 *   7. Loading spinner renders while isLoading=true.
 *   8. Detail dialog shows session_name and webhook_url as read-only.
 *   9. Detail dialog does NOT render editable session/server/webhook inputs.
 *  10. Paired success banner renders when status.paired=true.
 *
 * Mock strategy: mirrors Conexoes.test.tsx
 *   · ONE vi.mock per module (hoisted). Multiple mocks of the same module
 *     collide; the last wins silently.
 *   · All hooks are vi.fn()s configured per-test in beforeEach.
 *   · localStorage/sessionStorage provisioned by the shared seed vitest
 *     setup (seed/framework/frontend/vitest.setup.ts) — no per-file polyfill.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ────────────────────────────────────────────────────────────

const mockUseWhatsAppConnections = vi.fn();
const mockUseWhatsAppConnectionMutations = vi.fn();
const mockUseWhatsAppConnectionStatus = vi.fn();
const mockUseWhatsAppConnectionQr = vi.fn();
const mockUseWhatsAppConnectionActions = vi.fn();
const mockUseRevealApiKey = vi.fn();

vi.mock("@/hooks/useWhatsAppConnections", () => ({
  useWhatsAppConnections: mockUseWhatsAppConnections,
  useWhatsAppConnectionMutations: mockUseWhatsAppConnectionMutations,
  useWhatsAppConnectionStatus: mockUseWhatsAppConnectionStatus,
  useWhatsAppConnectionQr: mockUseWhatsAppConnectionQr,
  useWhatsAppConnectionActions: mockUseWhatsAppConnectionActions,
  useRevealApiKey: mockUseRevealApiKey,
}));

// Minimal UI stubs
vi.mock("@/components/ui/separator", () => ({ Separator: () => null }));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: any) => <span>{children}</span>,
}));
vi.mock("@/components/ui/card", () => ({
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardContent: () => null,
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
      value={value}
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
  Dialog: ({ children, open }: any) => open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children, open }: any) => open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogContent: ({ children }: any) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: any) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: any) => <h3>{children}</h3>,
  AlertDialogDescription: ({ children }: any) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: any) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: any) => <button>{children}</button>,
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

// ─── Fixtures ──────────────────────────────────────────────────────────────

const makeLine = (overrides: Partial<{
  id: string; label: string; session_name: string; webhook_url: string | null;
}> = {}) => ({
  id: overrides.id ?? "conn-1",
  label: overrides.label ?? "Atendimento SP",
  base_url: "http://waha:3000",
  session_name: overrides.session_name ?? "sw_conn1",
  webhook_url: overrides.webhook_url ?? "https://social.noctusai.com/api/whatsapp/webhook/abc123",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
});

// ─── Default hook returns ──────────────────────────────────────────────────

const makeDefaultMutations = () => ({
  create: { mutate: vi.fn(), isPending: false, isError: false },
  update: { mutate: vi.fn(), isPending: false, isError: false },
  remove: { mutate: vi.fn(), isPending: false, isError: false },
});

const makeDefaultActions = () => ({
  start: { mutate: vi.fn(), isPending: false },
  restart: { mutate: vi.fn(), isPending: false },
  logout: { mutate: vi.fn(), isPending: false },
  configureWebhook: { mutate: vi.fn(), isPending: false },
});

beforeEach(() => {
  mockUseWhatsAppConnections.mockReturnValue({ data: [], isLoading: false });
  mockUseWhatsAppConnectionMutations.mockReturnValue(makeDefaultMutations());
  mockUseWhatsAppConnectionStatus.mockReturnValue({ data: null });
  mockUseWhatsAppConnectionQr.mockReturnValue({ data: null });
  mockUseWhatsAppConnectionActions.mockReturnValue(makeDefaultActions());
  mockUseRevealApiKey.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ connection_id: "c", api_key: "revealed-key" }),
    isPending: false,
  });
});

// ─── Helpers ──────────────────────────────────────────────────────────────

async function renderWhatsAppConnections() {
  const { WhatsAppConnections } = await import("./Conexao");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(WhatsAppConnections)), fireEvent: rtl.fireEvent };
}

// ─── Tests ────────────────────────────────────────────────────────────────

describe("WhatsAppConnections — empty + loading states", () => {
  it("shows loading spinner while connections are loading", async () => {
    mockUseWhatsAppConnections.mockReturnValue({ data: [], isLoading: true });
    const { getByTestId } = await renderWhatsAppConnections();
    expect(getByTestId("loading-connections")).toBeTruthy();
  });

  it("shows empty-state card when no connections exist", async () => {
    const { getByTestId } = await renderWhatsAppConnections();
    expect(getByTestId("card")).toBeTruthy();
  });

  it("shows Nova conexão button", async () => {
    const { getByTestId } = await renderWhatsAppConnections();
    expect(getByTestId("btn-nova-conexao")).toBeTruthy();
  });
});

describe("CreateConnectionDialog — trimmed form (2 fields)", () => {
  it("opens create dialog on Nova conexão click", async () => {
    const { getByTestId, fireEvent } = await renderWhatsAppConnections();
    fireEvent.click(getByTestId("btn-nova-conexao"));
    expect(getByTestId("dialog")).toBeTruthy();
  });

  it("create dialog renders exactly the label and api_key inputs", async () => {
    const { getByTestId, fireEvent, queryByPlaceholderText } = await renderWhatsAppConnections();
    fireEvent.click(getByTestId("btn-nova-conexao"));
    expect(getByTestId("create-conn-label")).toBeTruthy();
    expect(getByTestId("create-conn-apikey")).toBeTruthy();
    // session / server / webhook inputs must NOT exist
    expect(queryByPlaceholderText(/default/i)).toBeNull();
    expect(queryByPlaceholderText(/servidor waha/i)).toBeNull();
    expect(queryByPlaceholderText(/webhook/i)).toBeNull();
  });

  it("submit button is disabled when label is empty", async () => {
    const { getByTestId, fireEvent } = await renderWhatsAppConnections();
    fireEvent.click(getByTestId("btn-nova-conexao"));
    const submitBtn = getByTestId("create-conn-submit") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
  });

  it("submit button is disabled when api_key is empty", async () => {
    const { getByTestId, fireEvent } = await renderWhatsAppConnections();
    fireEvent.click(getByTestId("btn-nova-conexao"));
    const labelInput = getByTestId("create-conn-label") as HTMLInputElement;
    fireEvent.change(labelInput, { target: { value: "Test" } });
    const submitBtn = getByTestId("create-conn-submit") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
  });

  it("submit button is enabled when both fields are filled", async () => {
    const { getByTestId, fireEvent } = await renderWhatsAppConnections();
    fireEvent.click(getByTestId("btn-nova-conexao"));
    fireEvent.change(getByTestId("create-conn-label") as HTMLInputElement, {
      target: { value: "Atendimento SP" },
    });
    fireEvent.change(getByTestId("create-conn-apikey") as HTMLInputElement, {
      target: { value: "my-api-key-123" },
    });
    const submitBtn = getByTestId("create-conn-submit") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(false);
  });

  it("create mutation receives only { label, api_key } — no extra fields", async () => {
    const createMutate = vi.fn();
    mockUseWhatsAppConnectionMutations.mockReturnValue({
      ...makeDefaultMutations(),
      create: { mutate: createMutate, isPending: false },
    });

    const { getByTestId, fireEvent } = await renderWhatsAppConnections();
    fireEvent.click(getByTestId("btn-nova-conexao"));
    fireEvent.change(getByTestId("create-conn-label") as HTMLInputElement, {
      target: { value: "Atendimento SP" },
    });
    fireEvent.change(getByTestId("create-conn-apikey") as HTMLInputElement, {
      target: { value: "secret-key" },
    });
    fireEvent.click(getByTestId("create-conn-submit"));

    expect(createMutate).toHaveBeenCalledOnce();
    const [body] = createMutate.mock.calls[0];
    expect(body).toEqual({ label: "Atendimento SP", api_key: "secret-key" });
    // Must NOT contain session_name, base_url, or webhook_url
    expect(body).not.toHaveProperty("session_name");
    expect(body).not.toHaveProperty("base_url");
    expect(body).not.toHaveProperty("webhook_url");
  });
});

describe("Create → QR auto-flow", () => {
  it("after successful create the detail dialog opens (autoStart mode)", async () => {
    const newLine = makeLine();
    let successCallback: ((line: any) => void) | undefined;

    const createMutate = vi.fn((_body: any, opts: any) => {
      successCallback = opts.onSuccess;
    });
    mockUseWhatsAppConnectionMutations.mockReturnValue({
      ...makeDefaultMutations(),
      create: { mutate: createMutate, isPending: false },
    });

    const { getByTestId, fireEvent } = await renderWhatsAppConnections();

    // Open create dialog and fill form
    fireEvent.click(getByTestId("btn-nova-conexao"));
    fireEvent.change(getByTestId("create-conn-label") as HTMLInputElement, {
      target: { value: "Atendimento SP" },
    });
    fireEvent.change(getByTestId("create-conn-apikey") as HTMLInputElement, {
      target: { value: "secret-key" },
    });
    fireEvent.click(getByTestId("create-conn-submit"));

    // Simulate successful create response with derived fields
    const React = (await import("react")).default;
    const { act } = await import("@testing-library/react");
    await act(async () => {
      successCallback?.(newLine);
    });

    // Detail dialog should now be open (autoStart path)
    // The dialog mock renders when open=true
    expect(getByTestId("dialog")).toBeTruthy();
  });

  it("start mutation is triggered on autoStart (auto-fires on render)", async () => {
    const startMutate = vi.fn();
    mockUseWhatsAppConnectionActions.mockReturnValue({
      ...makeDefaultActions(),
      start: { mutate: startMutate, isPending: false },
    });

    // Render the ConnectionDetailDialog directly with autoStart=true
    const { default: React } = await import("react");

    // Since ConnectionDetailDialog is not exported, we test the autoStart
    // effect indirectly: if we create a line and trigger the success callback,
    // the WhatsAppConnections component will render the detail dialog with
    // autoStart=true, which calls start.mutate(id) on first render.
    const newLine = makeLine({ id: "conn-new" });
    let successCallback: ((line: any) => void) | undefined;

    const createMutate = vi.fn((_body: any, opts: any) => {
      successCallback = opts.onSuccess;
    });
    mockUseWhatsAppConnectionMutations.mockReturnValue({
      ...makeDefaultMutations(),
      create: { mutate: createMutate, isPending: false },
    });

    const rtl = await import("@testing-library/react");
    const { getByTestId } = rtl.render(
      React.createElement((await import("./Conexao")).WhatsAppConnections),
    );

    rtl.fireEvent.click(getByTestId("btn-nova-conexao"));
    rtl.fireEvent.change(getByTestId("create-conn-label") as HTMLInputElement, {
      target: { value: "Test" },
    });
    rtl.fireEvent.change(getByTestId("create-conn-apikey") as HTMLInputElement, {
      target: { value: "key" },
    });
    rtl.fireEvent.click(getByTestId("create-conn-submit"));

    await rtl.act(async () => {
      successCallback?.(newLine);
    });

    // autoStart=true causes start.mutate to be called with the new line's id
    expect(startMutate).toHaveBeenCalledWith("conn-new");
  });
});

describe("ConnectionDetailDialog — read-only derived fields", () => {
  it("shows session_name and webhook_url as read-only info", async () => {
    const line = makeLine({
      session_name: "sw_atendimento_sp",
      webhook_url: "https://social.noctusai.com/api/whatsapp/webhook/tok123",
    });
    mockUseWhatsAppConnections.mockReturnValue({ data: [line], isLoading: false });
    mockUseWhatsAppConnectionStatus.mockReturnValue({
      data: { connection_id: line.id, status: "STOPPED", paired: false, me_id: null, me_name: null, session: line.session_name, error: null },
    });

    const { getByTestId, getByText, fireEvent } = await renderWhatsAppConnections();

    // Click the connection row to open the detail dialog
    const rowBtn = getByText("Atendimento SP");
    fireEvent.click(rowBtn.closest("button")!);

    expect(getByTestId("detail-session-name").textContent).toBe("sw_atendimento_sp");
    expect(getByTestId("detail-webhook-url").textContent).toBe(
      "https://social.noctusai.com/api/whatsapp/webhook/tok123",
    );
  });

  it("detail dialog does NOT contain editable session / server / webhook inputs", async () => {
    const line = makeLine();
    mockUseWhatsAppConnections.mockReturnValue({ data: [line], isLoading: false });

    const { getByText, fireEvent, queryByPlaceholderText } = await renderWhatsAppConnections();
    fireEvent.click(getByText("Atendimento SP").closest("button")!);

    expect(queryByPlaceholderText(/default/i)).toBeNull();
    expect(queryByPlaceholderText(/servidor waha/i)).toBeNull();
    expect(queryByPlaceholderText(/webhook/i)).toBeNull();
  });

  it("shows paired success banner when status.paired=true", async () => {
    const line = makeLine();
    mockUseWhatsAppConnections.mockReturnValue({ data: [line], isLoading: false });
    mockUseWhatsAppConnectionStatus.mockReturnValue({
      data: {
        connection_id: line.id,
        status: "WORKING",
        paired: true,
        me_id: "+5511999999999",
        me_name: "João Raphael",
        session: line.session_name,
        error: null,
      },
    });

    const { getByText, fireEvent, getByTestId } = await renderWhatsAppConnections();
    fireEvent.click(getByText("Atendimento SP").closest("button")!);

    expect(getByTestId("paired-success")).toBeTruthy();
  });

  it("API key field: masked by default → eye reveals → pencil enters edit mode", async () => {
    const revealMutate = vi
      .fn()
      .mockResolvedValue({ connection_id: "conn-1", api_key: "revealed-key" });
    mockUseRevealApiKey.mockReturnValue({ mutateAsync: revealMutate, isPending: false });
    const line = makeLine();
    mockUseWhatsAppConnections.mockReturnValue({ data: [line], isLoading: false });

    const rtl = await import("@testing-library/react");
    const { getByText, getByTestId, queryByTestId } = await renderWhatsAppConnections();
    rtl.fireEvent.click(getByText("Atendimento SP").closest("button")!);

    // Masked by default; no editable input yet.
    expect((getByTestId("edit-conn-apikey-display") as HTMLInputElement).value).toBe("••••••••");
    expect(queryByTestId("edit-conn-apikey")).toBeNull();

    // Eye → reveal the stored key via the owner-scoped endpoint.
    await rtl.act(async () => {
      rtl.fireEvent.click(getByTestId("btn-apikey-reveal"));
    });
    expect(revealMutate).toHaveBeenCalledWith(line.id);
    expect((getByTestId("edit-conn-apikey-display") as HTMLInputElement).value).toBe("revealed-key");

    // Pencil → edit (rotate) mode: an editable input replaces the masked display.
    rtl.fireEvent.click(getByTestId("btn-apikey-edit"));
    expect(queryByTestId("edit-conn-apikey")).toBeTruthy();
    expect(queryByTestId("edit-conn-apikey-display")).toBeNull();
  });
});

/**
 * Agendamentos.test.tsx — the `scheduling` module's UI.
 *
 * The module shipped 15 endpoints and no frontend; these tests pin that every
 * tab renders all four states honestly and that each surface is wired to the
 * route it claims.
 *
 * Covers:
 *   1-4. Agenda: skeleton / error / empty / rows (ids rendered as names).
 *   5.   Agenda: the settled-but-empty state renders EMPTY, never blank.
 *   6.   Agenda: the status filter is present.
 *   7-9. Propor: idle / results / empty-result.
 *   10.  Propor: submit is gated on both required fields.
 *   11.  Cadastros: all four ResourceManager surfaces mount on their own path.
 *   12-14. Identidades: empty / rows / resolve calls PATCH with the assignee.
 *   15.  Identidades: "Vincular" without an assignee does not call the mutation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ──────────────────────────────────────────────────────────────

const mockUseAppointments = vi.fn();
const mockUseAppointmentRequests = vi.fn();
const mockUsePendingChatIdentities = vi.fn();
const mockUseSchedulingUsers = vi.fn();
const mockUseSchedulingProperties = vi.fn();
const mockUseSchedulingCondominiums = vi.fn();
const mockResolveMutate = vi.fn();
const mockProposeMutate = vi.fn();

vi.mock("@/hooks/useScheduling", () => ({
  useAppointments: (...a: any[]) => mockUseAppointments(...a),
  useAppointmentRequests: () => mockUseAppointmentRequests(),
  usePendingChatIdentities: () => mockUsePendingChatIdentities(),
  useSchedulingUsers: () => mockUseSchedulingUsers(),
  useSchedulingProperties: () => mockUseSchedulingProperties(),
  useSchedulingCondominiums: () => mockUseSchedulingCondominiums(),
  useResolvePendingChatIdentity: () => ({
    mutate: mockResolveMutate,
    isPending: false,
  }),
  useProposeSlots: () => ({ mutate: mockProposeMutate, isPending: false }),
}));

// ResourceManager is the canonical organ — assert it is MOUNTED on the right
// apiPath rather than re-testing CRUD the organ already owns tests for.
vi.mock("@noctusai/lib/components", () => ({
  ResourceManager: ({ title, apiPath }: any) => (
    <div data-testid={`resource-manager:${apiPath}`}>{title}</div>
  ),
}));
vi.mock("@/lib/api", () => ({ api: {} }));

// ─── UI stubs ────────────────────────────────────────────────────────────────

vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: any) => <div data-testid="skeleton" className={className} />,
}));
vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: any) => <span>{children}</span>,
}));
vi.mock("@/components/ui/card", () => ({
  Card: ({ children, ...p }: any) => <div {...p}>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children, ...p }: any) => <div {...p}>{children}</div>,
}));
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, "data-testid": dt, type }: any) => (
    <button onClick={onClick} disabled={disabled} data-testid={dt} type={type}>
      {children}
    </button>
  ),
}));
vi.mock("@/components/ui/input", () => ({
  Input: ({ onChange, value, "data-testid": dt, type, id }: any) => (
    <input id={id} type={type ?? "text"} value={value ?? ""} onChange={onChange} data-testid={dt} />
  ),
}));
vi.mock("@/components/ui/label", () => ({
  Label: ({ children, htmlFor }: any) => <label htmlFor={htmlFor}>{children}</label>,
}));
// The Select stub keeps onValueChange reachable so the assignee flow is testable.
vi.mock("@/components/ui/select", () => ({
  Select: ({ children, onValueChange, disabled }: any) => (
    <div data-disabled={disabled ? "true" : "false"}>
      <button
        data-testid="select-pick"
        onClick={() => onValueChange?.("user-1")}
      />
      {children}
    </div>
  ),
  SelectTrigger: ({ children, "data-testid": dt }: any) => <div data-testid={dt}>{children}</div>,
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children }: any) => <div>{children}</div>,
}));
// Tabs stub renders EVERY panel so one render exercises all four.
vi.mock("@/components/ui/tabs", () => ({
  Tabs: ({ children }: any) => <div>{children}</div>,
  TabsList: ({ children }: any) => <div>{children}</div>,
  TabsTrigger: ({ children }: any) => <button>{children}</button>,
  TabsContent: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

// ─── Fixtures ────────────────────────────────────────────────────────────────

const settled = (data: any) => ({
  data,
  isPending: false,
  isFetching: false,
  isError: false,
  error: null,
});

const appointment = (over: Partial<any> = {}) => ({
  id: "appt-1",
  org_id: "org-1",
  appointment_request_id: null,
  google_calendar_event_id: null,
  property_id: "prop-1",
  condominium_id: "condo-1",
  media_crew_user_id: "user-1",
  route_group_id: null,
  start_at: "2026-09-10T13:00:00Z",
  end_at: "2026-09-10T14:00:00Z",
  status: "scheduled",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  ...over,
});

const identity = (over: Partial<any> = {}) => ({
  id: "pend-1",
  org_id: "org-1",
  chat_id: "5511999998888@c.us",
  push_name: "Marina",
  phone_hint: "+55 11 99999-8888",
  status: "pending",
  captured_at: "2026-09-01T10:00:00Z",
  resolved_at: null,
  resolved_to_user_id: null,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAppointments.mockReturnValue(settled([]));
  mockUseAppointmentRequests.mockReturnValue(settled([]));
  mockUsePendingChatIdentities.mockReturnValue(settled([]));
  mockUseSchedulingUsers.mockReturnValue(
    settled([
      { id: "user-1", name: "Ana Crew", role: "media_crew" },
      { id: "user-2", name: "Bruno Corretor", role: "real_estate_agent" },
    ]),
  );
  mockUseSchedulingProperties.mockReturnValue(
    settled([{ id: "prop-1", code: "AP-1203", unit: "1203" }]),
  );
  mockUseSchedulingCondominiums.mockReturnValue(
    settled([{ id: "condo-1", name: "Edifício Aurora" }]),
  );
});

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Agendamentos } = await import("./Agendamentos");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Agendamentos)), fireEvent: rtl.fireEvent };
}

// ─── Agenda ──────────────────────────────────────────────────────────────────

describe("Agendamentos — Agenda", () => {
  it("renders the skeleton while the first fetch is in flight", async () => {
    mockUseAppointments.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("agenda-loading")).toBeTruthy();
  });

  it("renders the error card on failure", async () => {
    mockUseAppointments.mockReturnValue({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: true,
      error: new Error("boom"),
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("agenda-error")).toBeTruthy();
  });

  it("renders the empty state when there are no appointments", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("agenda-empty")).toBeTruthy();
  });

  // Regression — the blank-page hole: settled, no error, no data. Every list
  // on this page must resolve to the EMPTY branch here, never to nothing.
  it("renders the empty state — not a blank panel — when settled with no data", async () => {
    mockUseAppointments.mockReturnValue({
      data: undefined,
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("agenda-empty")).toBeTruthy();
  });

  it("renders a row and resolves property/condo/crew ids to names", async () => {
    mockUseAppointments.mockReturnValue(settled([appointment()]));
    const { getByTestId } = await renderPage();
    const row = getByTestId("agenda-row-appt-1");
    expect(row.textContent).toContain("Edifício Aurora");
    expect(row.textContent).toContain("AP-1203");
    expect(row.textContent).toContain("Ana Crew");
    expect(row.textContent).toContain("Agendado");
  });

  it("exposes the appointment status filter", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("agenda-status-filter")).toBeTruthy();
  });

  it("renders the requests empty state independently of appointments", async () => {
    mockUseAppointments.mockReturnValue(settled([appointment()]));
    const { getByTestId } = await renderPage();
    expect(getByTestId("requests-empty")).toBeTruthy();
  });
});

// ─── Propor ──────────────────────────────────────────────────────────────────

describe("Agendamentos — Propor", () => {
  it("starts idle with no results table", async () => {
    const { getByTestId, queryByTestId } = await renderPage();
    expect(getByTestId("propose-idle")).toBeTruthy();
    expect(queryByTestId("propose-results")).toBeNull();
  });

  it("keeps submit disabled until code and date are both filled", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    expect((getByTestId("propose-submit") as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(getByTestId("propose-code"), { target: { value: "AP-1203" } });
    expect((getByTestId("propose-submit") as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(getByTestId("propose-date"), { target: { value: "2026-09-10" } });
    expect((getByTestId("propose-submit") as HTMLButtonElement).disabled).toBe(false);
  });

  it("submits the propose payload the backend declares", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.change(getByTestId("propose-code"), { target: { value: "AP-1203" } });
    fireEvent.change(getByTestId("propose-date"), { target: { value: "2026-09-10" } });
    fireEvent.click(getByTestId("propose-submit"));

    expect(mockProposeMutate).toHaveBeenCalledTimes(1);
    expect(mockProposeMutate.mock.calls[0][0]).toEqual({
      property_code: "AP-1203",
      requested_date: "2026-09-10",
      time_window: "any",
    });
  });

  it("renders returned slots", async () => {
    mockProposeMutate.mockImplementation((_body: any, opts: any) =>
      opts.onSuccess({
        property_code: "AP-1203",
        slots: [
          {
            start_at: "2026-09-10T13:00:00Z",
            end_at: "2026-09-10T14:00:00Z",
            duration_minutes: 60,
            score: 0.92,
          },
        ],
      }),
    );
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.change(getByTestId("propose-code"), { target: { value: "AP-1203" } });
    fireEvent.change(getByTestId("propose-date"), { target: { value: "2026-09-10" } });
    fireEvent.click(getByTestId("propose-submit"));
    expect(getByTestId("propose-results")).toBeTruthy();
  });

  it("renders the empty state when the engine returns no slot", async () => {
    mockProposeMutate.mockImplementation((_body: any, opts: any) =>
      opts.onSuccess({ property_code: "AP-1203", slots: [] }),
    );
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.change(getByTestId("propose-code"), { target: { value: "AP-1203" } });
    fireEvent.change(getByTestId("propose-date"), { target: { value: "2026-09-10" } });
    fireEvent.click(getByTestId("propose-submit"));
    expect(getByTestId("propose-empty")).toBeTruthy();
  });
});

// ─── Cadastros ───────────────────────────────────────────────────────────────

describe("Agendamentos — Cadastros", () => {
  it("mounts a ResourceManager on each of the four scheduling CRUD paths", async () => {
    const { getByTestId } = await renderPage();
    for (const path of [
      "/api/scheduling/condominiums",
      "/api/scheduling/properties",
      "/api/scheduling/services",
      "/api/scheduling/users",
    ]) {
      expect(getByTestId(`resource-manager:${path}`)).toBeTruthy();
    }
  });
});

// ─── Identidades ─────────────────────────────────────────────────────────────

describe("Agendamentos — Identidades", () => {
  it("renders the empty state when nothing is pending", async () => {
    const { getByTestId } = await renderPage();
    expect(getByTestId("identidades-empty")).toBeTruthy();
  });

  it("renders a pending identity row", async () => {
    mockUsePendingChatIdentities.mockReturnValue(settled([identity()]));
    const { getByTestId } = await renderPage();
    const row = getByTestId("identidade-row-pend-1");
    expect(row.textContent).toContain("Marina");
  });

  it("does NOT call the mutation when linking with no assignee chosen", async () => {
    mockUsePendingChatIdentities.mockReturnValue(settled([identity()]));
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("identidade-link-pend-1"));
    expect(mockResolveMutate).not.toHaveBeenCalled();
  });

  it("resolves with the chosen assignee", async () => {
    mockUsePendingChatIdentities.mockReturnValue(settled([identity()]));
    const { getByTestId, fireEvent } = await renderPage();
    const { within } = await import("@testing-library/react");
    // Scope to the identity ROW — the agenda status filter is also a Select,
    // and it renders first, so an unscoped query would pick the wrong one.
    const row = getByTestId("identidade-row-pend-1");
    fireEvent.click(within(row).getByTestId("select-pick"));
    fireEvent.click(getByTestId("identidade-link-pend-1"));
    expect(mockResolveMutate).toHaveBeenCalledTimes(1);
    expect(mockResolveMutate.mock.calls[0][0]).toEqual({
      id: "pend-1",
      status: "resolved",
      resolvedToUserId: "user-1",
    });
  });

  it("rejects without requiring an assignee", async () => {
    mockUsePendingChatIdentities.mockReturnValue(settled([identity()]));
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("identidade-reject-pend-1"));
    expect(mockResolveMutate.mock.calls[0][0]).toEqual({
      id: "pend-1",
      status: "rejected",
      resolvedToUserId: null,
    });
  });
});

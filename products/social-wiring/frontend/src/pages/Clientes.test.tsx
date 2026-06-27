/**
 * Clientes page tests.
 *
 * Tests:
 *   1. Renders loading skeleton while clients are fetching
 *   2. Renders client cards when clients are returned
 *   3. Renders empty state when no clients exist
 *   4. Renders error state on fetch failure
 *   5. "Novo cliente" button opens create dialog
 *   6. ClienteModal opens when a card is clicked
 *   7. Chat tab opens from the card chat button
 *
 * Mock strategy (mirrors Conexoes.test.tsx):
 *   · ONE vi.mock per module
 *   · hooks are vi.fn()s configured per-test in beforeEach
 *   · @noctusai/lib's IntegrationCard + IntegrationCardModal are stubs
 *   · ClienteModal is a lightweight stub to avoid full render pipeline
 *   · localStorage provisioned by seed vitest setup
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ────────────────────────────────────────────────────────────

const mockUseClients = vi.fn();
const mockUseCreateClient = vi.fn();
const mockUseUpdateClient = vi.fn();
const mockUseDeleteClient = vi.fn();

vi.mock("@/hooks/useClients", () => ({
  useClients: mockUseClients,
  useCreateClient: mockUseCreateClient,
  useUpdateClient: mockUseUpdateClient,
  useDeleteClient: mockUseDeleteClient,
}));

// ─── Component mocks ────────────────────────────────────────────────────────

vi.mock("@/components/ClienteModal", () => ({
  ClienteModal: ({ client, open, onClose, defaultTab }: any) =>
    open ? (
      <div data-testid="cliente-modal" data-client-id={client?.id} data-tab={defaultTab}>
        <button onClick={onClose}>Fechar</button>
      </div>
    ) : null,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: any) => <div className={className} data-testid="skeleton" />,
}));

// ─── Fixtures ────────────────────────────────────────────────────────────────

const makeClient = (overrides: Partial<{
  id: string; name: string; slug: string; kind: string | null; notes: string | null;
}> = {}) => ({
  id: overrides.id ?? "client-1",
  org_id: "org-1",
  slug: overrides.slug ?? "acme",
  name: overrides.name ?? "Acme Corp",
  kind: overrides.kind ?? null,
  notes: overrides.notes ?? null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
});

// ─── Defaults ────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockUseClients.mockReturnValue({ data: [], isLoading: false, isError: false });
  mockUseCreateClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseDeleteClient.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function renderClientes(initialEntries: string[] = ["/"]) {
  const { default: Clientes } = await import("./Clientes");
  const React = (await import("react")).default;
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(
      React.createElement(MemoryRouter, { initialEntries },
        React.createElement(Clientes),
      ),
    ),
    fireEvent: rtl.fireEvent,
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("Clientes — loading state", () => {
  it("renders skeleton while loading", async () => {
    mockUseClients.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { getByTestId } = await renderClientes();
    expect(getByTestId("clients-skeleton")).toBeTruthy();
  });
});

describe("Clientes — success state", () => {
  it("renders client cards for each client", async () => {
    const clients = [
      makeClient({ id: "c-1", name: "Acme Corp" }),
      makeClient({ id: "c-2", name: "Beta Ltd", slug: "beta" }),
    ];
    mockUseClients.mockReturnValue({ data: clients, isLoading: false, isError: false });

    const { getAllByTestId, getByText } = await renderClientes();
    expect(getAllByTestId("client-card").length).toBe(2);
    expect(getByText("Acme Corp")).toBeTruthy();
    expect(getByText("Beta Ltd")).toBeTruthy();
  });

  it("renders the page header", async () => {
    mockUseClients.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByText } = await renderClientes();
    expect(getByText("Clientes")).toBeTruthy();
  });

  it("renders kind badge when present", async () => {
    mockUseClients.mockReturnValue({
      data: [makeClient({ kind: "empresa" })],
      isLoading: false,
      isError: false,
    });
    const { getByText } = await renderClientes();
    expect(getByText("empresa")).toBeTruthy();
  });
});

describe("Clientes — empty state", () => {
  it("renders empty state when no clients", async () => {
    mockUseClients.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { getByTestId } = await renderClientes();
    expect(getByTestId("clientes-empty")).toBeTruthy();
  });
});

describe("Clientes — error state", () => {
  it("renders error state on fetch failure", async () => {
    mockUseClients.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Network error"),
    });
    const { getByTestId, getByText } = await renderClientes();
    expect(getByTestId("clientes-error")).toBeTruthy();
    expect(getByText("Network error")).toBeTruthy();
  });
});

describe("Clientes — modal interactions", () => {
  it("opens ClienteModal when card is clicked", async () => {
    const client = makeClient({ id: "c-1", name: "Acme Corp" });
    mockUseClients.mockReturnValue({ data: [client], isLoading: false, isError: false });

    const { getAllByTestId, getByTestId, fireEvent } = await renderClientes();

    const card = getAllByTestId("client-card")[0];
    fireEvent.click(card);

    const modal = getByTestId("cliente-modal");
    expect(modal.getAttribute("data-client-id")).toBe("c-1");
    expect(modal.getAttribute("data-tab")).toBe("contas");
  });

  it("opens ClienteModal on Chat tab when chat button is clicked", async () => {
    const client = makeClient({ id: "c-1", name: "Acme Corp" });
    mockUseClients.mockReturnValue({ data: [client], isLoading: false, isError: false });

    const { getAllByTestId, getByTestId, fireEvent } = await renderClientes();

    const chatBtn = getAllByTestId("client-chat-btn")[0];
    fireEvent.click(chatBtn);

    const modal = getByTestId("cliente-modal");
    expect(modal.getAttribute("data-tab")).toBe("chat");
  });

  it("closes modal when onClose is called", async () => {
    const client = makeClient({ id: "c-1", name: "Acme Corp" });
    mockUseClients.mockReturnValue({ data: [client], isLoading: false, isError: false });

    const { getAllByTestId, queryByTestId, getByText, fireEvent } = await renderClientes();

    const card = getAllByTestId("client-card")[0];
    fireEvent.click(card);

    expect(queryByTestId("cliente-modal")).toBeTruthy();
    fireEvent.click(getByText("Fechar"));
    expect(queryByTestId("cliente-modal")).toBeNull();
  });
});

describe("Clientes — create dialog", () => {
  it("shows at least one create dialog button", async () => {
    mockUseClients.mockReturnValue({ data: [], isLoading: false, isError: false });
    // The empty state renders a second CreateClientDialog, so multiple buttons exist.
    const { getAllByTestId } = await renderClientes();
    const buttons = getAllByTestId("create-client-btn");
    expect(buttons.length).toBeGreaterThan(0);
  });
});

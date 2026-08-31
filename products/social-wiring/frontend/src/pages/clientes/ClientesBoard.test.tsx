/**
 * ClientesBoard.test.tsx — the board switch from leads to people
 * (PROJECT.md §6 Slice C, §8 checkpoint: "the board shows one card per
 * human"). Asserts: one card per cliente, the 399 keyless people
 * (`identidade_incerta`) render visibly distinct rather than reading as a
 * confirmed identity, the active/inactive tabs (D4), and restore (D4)
 * wiring through to `PATCH { ativo: true }`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

// Stub Radix Tabs with a real onValueChange wiring (context-based) rather
// than depending on Radix's own state machine in jsdom — same rationale as
// Settings.test.tsx, but this test DOES need the tab switch to actually
// fire, so children are wired through a tiny context instead of rendered
// unconditionally.
vi.mock("@/components/ui/tabs", async () => {
  const React = await import("react");
  const TabsCtx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  const Tabs = ({ onValueChange, children }: any) =>
    React.createElement(TabsCtx.Provider, { value: { onValueChange } }, children);
  const TabsList = ({ children }: any) => React.createElement("div", null, children);
  const TabsTrigger = ({ value, children, ...props }: any) => {
    const ctx = React.useContext(TabsCtx);
    return React.createElement(
      "button",
      { type: "button", onClick: () => ctx.onValueChange?.(value), ...props },
      children,
    );
  };
  return { Tabs, TabsList, TabsTrigger };
});

const mockUseClientesBoard = vi.fn();
const mockUpdate = { mutate: vi.fn(), isPending: false, variables: undefined as any };

vi.mock("@/hooks/useClientes", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useClientes")>(
    "@/hooks/useClientes",
  );
  return {
    ...actual,
    useClientesBoard: mockUseClientesBoard,
    useClienteMutations: () => ({ update: mockUpdate }),
  };
});

vi.mock("@/hooks/useLeadsCorretores", () => ({
  useLeadCorretores: () => ({ data: [{ id: "cor1", nome: "João" }] }),
}));

// lead-card-hub Phase 2: `ClienteDetailModal` pulls in the full `useCardHub`
// query surface (real `@tanstack/react-query` hooks) — this file has no
// `QueryClientProvider` (every OTHER data hook here is mocked at the hook
// level instead, never exercising react-query for real). Stubbed to a
// marker so this file stays focused on the BOARD's own wiring: which
// cliente id got opened, not the dialog's internals (covered by
// `ClienteCardDialog.test.tsx` + `useCardHub.test.ts`).
vi.mock("@/components/ClienteDetailModal", async () => {
  const React = await import("react");
  return {
    ClienteDetailModal: ({ clienteId, open }: { clienteId: string | null; open: boolean }) =>
      open ? React.createElement("div", { "data-testid": "cliente-detail-modal", "data-cliente-id": clienteId }) : null,
  };
});

function cliente(overrides: Partial<any> = {}) {
  return {
    id: "cl1",
    nome: "Maria Silva",
    chave_canonica: "+5511999998888",
    chave_tipo: "telefone",
    identidade_incerta: false,
    ativo: true,
    inativo_em: null,
    arquivado_em: null,
    primeiro_contato_em: "2026-01-01",
    ultimo_contato_em: "2026-08-01",
    touch_count: 4,
    atendimentos_abertos: 1,
    ...overrides,
  };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: ClientesBoard } = await import("./ClientesBoard");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(ClientesBoard)) };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUpdate.isPending = false;
  mockUpdate.variables = undefined;
});

describe("ClientesBoard — loading/error", () => {
  it("shows loading skeletons before any data has arrived", async () => {
    mockUseClientesBoard.mockReturnValue({
      isPending: true,
      isFetching: true,
      isError: false,
      data: undefined,
      refetch: vi.fn(),
    });
    const { queryByTestId } = await renderPage();
    expect(queryByTestId("cliente-card")).toBeNull();
  });

  it("shows the error state with a retry action", async () => {
    mockUseClientesBoard.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: true,
      data: undefined,
      refetch: vi.fn(),
    });
    const { getByText } = await renderPage();
    expect(getByText("Não foi possível carregar os clientes.")).toBeTruthy();
  });

  // The 2026-08-31 refetch-unmount bug: `isPending || isFetching` re-armed
  // the 8-skeleton grid on EVERY filter change / restore mutation, tearing
  // down the whole 8-card grid even though `placeholderData` keeps the
  // previous page's real cards on `data` the entire time. `isPending &&
  // !data` must keep them mounted through that refetch.
  it("keeps the existing cliente cards mounted during a background refetch (isPending false, isFetching true, data present)", async () => {
    mockUseClientesBoard.mockReturnValue({
      isPending: false,
      isFetching: true,
      isError: false,
      data: {
        items: [cliente({ id: "cl1", nome: "Maria Silva" })],
        total: 9320,
        page: 1,
        pages: 389,
      },
      refetch: vi.fn(),
    });
    // `loading`/success are mutually-exclusive branches in ClientesBoard's
    // own ternary — rendering the real card here proves the skeleton branch
    // did NOT win, without depending on a `data-testid` the Skeleton organ
    // doesn't carry.
    const { getAllByTestId } = await renderPage();
    expect(getAllByTestId("cliente-card")).toHaveLength(1);
  });
});

describe("ClientesBoard — one card per human", () => {
  beforeEach(() => {
    mockUseClientesBoard.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: {
        items: [
          cliente({ id: "cl1", nome: "Maria Silva" }),
          cliente({
            id: "cl2",
            nome: "Lead sem contato",
            chave_canonica: null,
            chave_tipo: null,
            identidade_incerta: true,
            touch_count: 1,
            atendimentos_abertos: 0,
          }),
        ],
        total: 9320,
        page: 1,
        pages: 389,
      },
      refetch: vi.fn(),
    });
  });

  it("renders one card per cliente", async () => {
    const { getAllByTestId } = await renderPage();
    expect(getAllByTestId("cliente-card")).toHaveLength(2);
  });

  it("shows the identidade-incerta badge on a keyless person, never a plain confirmed card", async () => {
    const { getAllByTestId, getByText } = await renderPage();
    const badges = getAllByTestId("cliente-identidade-incerta-badge");
    expect(badges).toHaveLength(1); // only the keyless one, not Maria
    expect(getByText("Sem contato identificado")).toBeTruthy();
  });

  it("does not mark the keyed cliente as identidade incerta", async () => {
    const { getByText } = await renderPage();
    expect(getByText("Maria Silva")).toBeTruthy();
    expect(getByText("+5511999998888")).toBeTruthy();
  });
});

describe("ClientesBoard — inactive tab + restore (D4)", () => {
  it("requests ativo=false only when the Inativos tab is active", async () => {
    mockUseClientesBoard.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: {
        items: [cliente({ id: "cl3", nome: "Pessoa Inativa", ativo: false })],
        total: 1,
        page: 1,
        pages: 1,
      },
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("clientes-tab-inativos"));

    expect(mockUseClientesBoard).toHaveBeenLastCalledWith(
      expect.objectContaining({ ativo: false }),
    );
  });

  it("shows a Restaurar button on an inactive card and PATCHes ativo: true", async () => {
    mockUseClientesBoard.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: {
        items: [cliente({ id: "cl3", nome: "Pessoa Inativa", ativo: false })],
        total: 1,
        page: 1,
        pages: 1,
      },
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("cliente-restaurar-btn"));

    expect(mockUpdate.mutate).toHaveBeenCalledWith({ id: "cl3", body: { ativo: true } });
  });
});

describe("ClientesBoard — click opens the card detail dialog (lead-card-hub Phase 2)", () => {
  beforeEach(() => {
    mockUseClientesBoard.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: {
        items: [cliente({ id: "cl1", nome: "Maria Silva" })],
        total: 1,
        page: 1,
        pages: 1,
      },
      refetch: vi.fn(),
    });
  });

  it("mounts no dialog until a card is clicked", async () => {
    const { queryByTestId } = await renderPage();
    expect(queryByTestId("cliente-detail-modal")).toBeNull();
  });

  it("clicking the card mounts the detail dialog for that cliente id", async () => {
    const { getByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("cliente-card"));

    const modal = getByTestId("cliente-detail-modal");
    expect(modal.getAttribute("data-cliente-id")).toBe("cl1");
  });

  it("clicking Restaurar does not also open the dialog", async () => {
    mockUseClientesBoard.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: {
        items: [cliente({ id: "cl3", nome: "Pessoa Inativa", ativo: false })],
        total: 1,
        page: 1,
        pages: 1,
      },
      refetch: vi.fn(),
    });
    const { getByTestId, queryByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("cliente-restaurar-btn"));

    expect(queryByTestId("cliente-detail-modal")).toBeNull();
  });
});

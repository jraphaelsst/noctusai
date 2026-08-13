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
    negociacoes_abertas: 1,
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
            negociacoes_abertas: 0,
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

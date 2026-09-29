/**
 * RevisaoFila.test.tsx — the review queue, this slice's primary deliverable.
 * Asserts: reason codes render, merge/manter-separados wire to the right
 * mutation, a resolved group is filtered out immediately (never reappears),
 * undo is reachable from the merge success toast, and an empty queue reads
 * as SUCCESS (not the generic empty/error look) — PROJECT.md §8's checkpoint.
 *
 * `@noctusai/seed/infra` is stubbed at module scope (same reason as
 * `PortalRoi.test.tsx`: `useClientesRevisao.ts` imports its `api` client at
 * module scope, and `vi.importActual` still executes that import). `sonner`
 * is stubbed to assert the undo toast's `action` prop directly, mirroring
 * `CampanhaManagerDialog.test.tsx`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// Stub Radix Tabs with a real onValueChange/value wiring (context-based)
// rather than depending on Radix's own pointer-event state machine in jsdom
// — same rationale as `ClientesBoard.test.tsx`'s own Tabs stub, extended
// with `TabsContent` (this page, unlike that board, gates real content on
// the active value rather than its own local conditional).
vi.mock("@/components/ui/tabs", async () => {
  const React = await import("react");
  const TabsCtx = React.createContext<{ value?: string; onValueChange?: (v: string) => void }>(
    {},
  );
  const Tabs = ({ value, onValueChange, children }: any) =>
    React.createElement(TabsCtx.Provider, { value: { value, onValueChange } }, children);
  const TabsList = ({ children, ...props }: any) => React.createElement("div", props, children);
  const TabsTrigger = ({ value, children, ...props }: any) => {
    const ctx = React.useContext(TabsCtx);
    return React.createElement(
      "button",
      { type: "button", onClick: () => ctx.onValueChange?.(value), ...props },
      children,
    );
  };
  const TabsContent = ({ value, children, ...props }: any) => {
    const ctx = React.useContext(TabsCtx);
    if (ctx.value !== value) return null;
    return React.createElement("div", props, children);
  };
  return { Tabs, TabsList, TabsTrigger, TabsContent };
});

const mockUseRevisaoFila = vi.fn();
const mockMerge = { mutate: vi.fn(), isPending: false, variables: undefined as any };
const mockManterSeparados = { mutate: vi.fn(), isPending: false, variables: undefined as any };
const mockDesfazer = { mutate: vi.fn(), isPending: false, variables: undefined as any };

const mockUseSegurosCount = vi.fn(() => ({ data: undefined, loading: false }));
const mockMergeSeguros = { mutate: vi.fn(), isPending: false };

// CPF axis (2026-09-28) — mocked for the same reason as every hook above:
// the real ones call TanStack directly and this suite deliberately does not
// mount a QueryClientProvider. `useRevisaoCpfFila`/`useRevisaoCpfMutations`
// are called UNCONDITIONALLY by `RevisaoFila` (both tabs' hooks run on every
// render, only the ACTIVE tab's content mounts) — left unmocked, they would
// throw "No QueryClient set" even on a render that never opens the CPF tab.
const mockUseRevisaoCpfFila = vi.fn(() => ({
  isPending: false,
  isFetching: false,
  isError: false,
  data: { items: [], total: 0, page: 1, pages: 1 },
  refetch: vi.fn(),
}));
const mockCpfMerge = { mutate: vi.fn(), isPending: false, variables: undefined as any };
const mockCpfManterSeparados = { mutate: vi.fn(), isPending: false, variables: undefined as any };

vi.mock("@/hooks/useClientesRevisao", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useClientesRevisao")>(
    "@/hooks/useClientesRevisao",
  );
  return {
    ...actual,
    useRevisaoFila: mockUseRevisaoFila,
    useRevisaoMutations: () => ({
      merge: mockMerge,
      manterSeparados: mockManterSeparados,
      desfazer: mockDesfazer,
    }),
    // The bulk-drain pair (2026-08-25). Mocked rather than left as the real
    // hooks: they call TanStack directly and would need a QueryClientProvider
    // this suite deliberately does not mount.
    useRevisaoSegurosCount: mockUseSegurosCount,
    useMergeSeguros: () => mockMergeSeguros,
    useRevisaoCpfFila: mockUseRevisaoCpfFila,
    useRevisaoCpfMutations: () => ({
      merge: mockCpfMerge,
      manterSeparados: mockCpfManterSeparados,
    }),
  };
});

// `useNegociacoesDoCliente` isn't exercised by this page directly, but
// `RevisaoCpfGrupoCard`'s per-candidate "Ver negociações" lazily calls it —
// mocked here too so a CPF-tab test that expands a candidate never hits the
// real TanStack hook without a provider.
vi.mock("@/hooks/useClientes", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useClientes")>(
    "@/hooks/useClientes",
  );
  return {
    ...actual,
    useNegociacoesDoCliente: vi.fn(() => ({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { cliente_id: "c1", negociacoes: [], total_negociacoes: 0, candidatos_pendentes: [] },
      refetch: vi.fn(),
    })),
  };
});

function grupo(overrides: Partial<any> = {}) {
  return {
    motivo: "C5",
    chave_canonica: "+5511974781330",
    candidatos: [
      { id: "cand1", nome: "Maria Silva", chave_canonica: "+5511974781330", touch_count: 4 },
      { id: "cand2", nome: "João Souza", chave_canonica: "+5511974781330", touch_count: 2 },
    ],
    ...overrides,
  };
}

/** A resolved queue page carrying `itens`. */
function pagina(itens: any[]) {
  return {
    isPending: false,
    isFetching: false,
    isError: false,
    data: { items: itens, total: itens.length, page: 1, pages: 1 },
    refetch: vi.fn(),
  };
}

async function renderPage(initialEntries: string[] = ["/clientes/revisao"]) {
  const React = (await import("react")).default;
  const { default: RevisaoFila } = await import("./RevisaoFila");
  const { MemoryRouter } = await import("react-router-dom");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(
      React.createElement(MemoryRouter, { initialEntries }, React.createElement(RevisaoFila)),
    ),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockMerge.isPending = false;
  mockMerge.variables = undefined;
  mockManterSeparados.isPending = false;
  mockManterSeparados.variables = undefined;
  mockCpfMerge.isPending = false;
  mockCpfMerge.variables = undefined;
  mockCpfManterSeparados.isPending = false;
  mockCpfManterSeparados.variables = undefined;
  mockUseRevisaoCpfFila.mockReturnValue({
    isPending: false,
    isFetching: false,
    isError: false,
    data: { items: [], total: 0, page: 1, pages: 1 },
    refetch: vi.fn(),
  });
});

describe("RevisaoFila — loading", () => {
  it("shows the loading skeleton before any data has arrived", async () => {
    mockUseRevisaoFila.mockReturnValue({
      isPending: true,
      isFetching: true,
      isError: false,
      data: undefined,
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("revisao-loading")).toBeTruthy();
  });
});

describe("RevisaoFila — error", () => {
  it("shows the error state with a retry action", async () => {
    mockUseRevisaoFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: true,
      data: undefined,
      refetch: vi.fn(),
    });
    const { getByText } = await renderPage();
    expect(getByText("Não foi possível carregar a fila de revisão.")).toBeTruthy();
  });
});

describe("RevisaoFila — empty queue (success, not failure)", () => {
  it("renders the positive success state, not the error/empty-filtered look", async () => {
    mockUseRevisaoFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { items: [], total: 0, page: 1, pages: 1 },
      refetch: vi.fn(),
    });
    const { getByTestId, getByText, queryByText } = await renderPage();
    expect(getByTestId("revisao-empty-success")).toBeTruthy();
    expect(getByText("Fila de revisão vazia — tudo certo!")).toBeTruthy();
    expect(queryByText("Não foi possível carregar a fila de revisão.")).toBeNull();
  });
});

describe("RevisaoFila — groups to review", () => {
  const twoGroups = {
    items: [
      grupo({ motivo: "C5" }),
      grupo({
        motivo: "C4",
        chave_canonica: "+5511900000000",
        candidatos: [
          { id: "cand3", nome: "Ana", chave_canonica: "+5511900000000", touch_count: 1 },
          { id: "cand4", nome: "Ana Paula", chave_canonica: "+5511900000000", touch_count: 3 },
        ],
      }),
    ],
    total: 311,
    page: 1,
    pages: 26,
  };

  beforeEach(() => {
    mockUseRevisaoFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: twoGroups,
      refetch: vi.fn(),
    });
  });

  it("renders every group with its reason code and every candidate", async () => {
    const { getAllByTestId, getByText } = await renderPage();
    expect(getAllByTestId("revisao-grupo-card")).toHaveLength(2);
    expect(getByText(/C5 ·/)).toBeTruthy();
    expect(getByText(/C4 ·/)).toBeTruthy();
    expect(getByText("Maria Silva")).toBeTruthy();
    expect(getByText("Ana Paula")).toBeTruthy();
    expect(getByText(/^311 grupo\(s\) aguardando revisão\.$/)).toBeTruthy();
  });

  it("calls merge.mutate with the clicked group's id", async () => {
    const { getAllByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");
    const [mesclarBtn] = getAllByTestId("revisao-mesclar-btn");
    fireEvent.click(mesclarBtn);
    expect(mockMerge.mutate).toHaveBeenCalledWith(
      { grupoId: "+5511974781330" },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it("calls manterSeparados.mutate with the clicked group's id", async () => {
    const { getAllByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");
    const [manterBtn] = getAllByTestId("revisao-manter-separados-btn");
    fireEvent.click(manterBtn);
    expect(mockManterSeparados.mutate).toHaveBeenCalledWith(
      "+5511974781330",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("filters a resolved group out immediately (does not reappear) and surfaces an undo toast", async () => {
    const { toast } = await import("sonner");
    const { getAllByTestId, queryByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    // Simulate the mutate call invoking its onSuccess callback, as the real
    // mutation would after a successful POST.
    mockManterSeparados.mutate.mockImplementation((_grupoId: string, opts: any) => {
      opts?.onSuccess?.();
    });

    expect(getAllByTestId("revisao-grupo-card")).toHaveLength(2);
    const [manterBtn] = getAllByTestId("revisao-manter-separados-btn");
    fireEvent.click(manterBtn);

    // g1 is gone from the render; g2 remains — position preserved, no resurface.
    expect(getAllByTestId("revisao-grupo-card")).toHaveLength(1);
    expect(queryByTestId("revisao-grupo-card")?.getAttribute("data-motivo")).toBe("C4");
    expect(toast.success).toHaveBeenCalledWith(
      "Mantidos separados.",
      expect.objectContaining({ description: expect.stringContaining("não vai mais aparecer") }),
    );
  });

  it("wires the merge success toast's 'Desfazer' action to desfazer.mutate with the returned merge_id", async () => {
    const { toast } = await import("sonner");
    mockMerge.mutate.mockImplementation((_vars: any, opts: any) => {
      opts?.onSuccess?.({ merge_id: "m-abc" });
    });

    const { getAllByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");
    const [mesclarBtn] = getAllByTestId("revisao-mesclar-btn");
    fireEvent.click(mesclarBtn);

    expect(toast.success).toHaveBeenCalledWith(
      "Grupo mesclado.",
      expect.objectContaining({
        action: expect.objectContaining({ label: "Desfazer", onClick: expect.any(Function) }),
      }),
    );

    // Fire the action's onClick — it must call desfazer with the merge_id.
    const call = (toast.success as any).mock.calls[0];
    call[1].action.onClick();
    expect(mockDesfazer.mutate).toHaveBeenCalledWith("m-abc", expect.any(Object));
  });
});

// ─── Bulk drain + keyboard (2026-08-25) ─────────────────────────────────────
describe("RevisaoFila — esvaziando a fila", () => {
  it("hides the bulk banner when nothing is unambiguous", async () => {
    mockUseSegurosCount.mockReturnValue({
      data: { grupos_mesclados: 0, clientes_absorvidos: 0, grupos_restantes: 12 },
      loading: false,
    });
    mockUseRevisaoFila.mockReturnValue(pagina([grupo()]));

    const { queryByTestId } = await renderPage();

    expect(queryByTestId("revisao-seguros-banner")).toBeNull();
  });

  it("names its own size before the operator presses it", async () => {
    // A bulk action that will not say how much it changes is one people are
    // right not to press — and this queue's problem is that nobody pressed.
    mockUseSegurosCount.mockReturnValue({
      data: { grupos_mesclados: 81, clientes_absorvidos: 92, grupos_restantes: 270 },
      loading: false,
    });
    mockUseRevisaoFila.mockReturnValue(pagina([grupo()]));

    const { getByTestId } = await renderPage();

    expect(getByTestId("revisao-merge-seguros-btn").textContent).toContain("81");
  });

  it("J moves the cursor and M merges the card it is on", async () => {
    mockUseSegurosCount.mockReturnValue({
      data: { grupos_mesclados: 0, clientes_absorvidos: 0, grupos_restantes: 2 },
      loading: false,
    });
    const a = grupo({ chave_canonica: "+5511900000001" });
    const b = grupo({ chave_canonica: "+5511900000002" });
    mockUseRevisaoFila.mockReturnValue(pagina([a, b]));

    await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.keyDown(window, { key: "j" });
    fireEvent.keyDown(window, { key: "m" });

    expect(mockMerge.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ grupoId: "+5511900000002" }),
      expect.anything(),
    );
  });

  it("S keeps the focused group separate", async () => {
    mockUseSegurosCount.mockReturnValue({
      data: { grupos_mesclados: 0, clientes_absorvidos: 0, grupos_restantes: 1 },
      loading: false,
    });
    mockUseRevisaoFila.mockReturnValue(pagina([grupo({ chave_canonica: "+5511900000009" })]));

    await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.keyDown(window, { key: "s" });

    expect(mockManterSeparados.mutate).toHaveBeenCalledWith(
      "+5511900000009",
      expect.anything(),
    );
  });

  it("ignores the shortcuts while the operator is typing", async () => {
    // 🔴 Otherwise typing "mesclar" into a search box merges four groups.
    mockUseSegurosCount.mockReturnValue({
      data: { grupos_mesclados: 0, clientes_absorvidos: 0, grupos_restantes: 1 },
      loading: false,
    });
    mockUseRevisaoFila.mockReturnValue(pagina([grupo()]));

    await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "m" });

    expect(mockMerge.mutate).not.toHaveBeenCalled();
  });
});

// ─── CPF axis (2026-09-28) ───────────────────────────────────────────────────

function cpfCandidato(overrides: Partial<any> = {}) {
  return { id: "cli1", nome: "Maria Silva", cpf: "12345678901", ...overrides };
}

function cpfGrupo(overrides: Partial<any> = {}) {
  return {
    motivo: "CPF",
    chave_canonica: "12345678901",
    candidatos: [cpfCandidato(), cpfCandidato({ id: "cli2", nome: "Maria S. Silva" })],
    ...overrides,
  };
}

describe("RevisaoFila — CPF tab", () => {
  it("starts on the Identidade tab and switches to CPF on click", async () => {
    mockUseRevisaoFila.mockReturnValue(pagina([grupo()]));
    const { getByTestId, queryByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    expect(getByTestId("revisao-grupo-card")).toBeTruthy();
    expect(queryByTestId("revisao-cpf-grupo-card")).toBeNull();

    fireEvent.click(getByTestId("revisao-tab-cpf"));

    expect(queryByTestId("revisao-grupo-card")).toBeNull();
  });

  it("deep-links straight into the CPF tab via ?tab=cpf", async () => {
    mockUseRevisaoFila.mockReturnValue(pagina([grupo()]));
    mockUseRevisaoCpfFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { items: [cpfGrupo()], total: 1, page: 1, pages: 1 },
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderPage(["/clientes/revisao?tab=cpf"]);
    expect(getByTestId("revisao-cpf-grupo-card")).toBeTruthy();
  });

  it("shows the empty-success state when there is nothing to review", async () => {
    mockUseRevisaoFila.mockReturnValue(pagina([]));
    mockUseRevisaoCpfFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { items: [], total: 0, page: 1, pages: 1 },
      refetch: vi.fn(),
    });
    const { getByTestId, getByText, fireEvent } = { ...(await renderPage()), fireEvent: (await import("@testing-library/react")).fireEvent };
    fireEvent.click(getByTestId("revisao-tab-cpf"));
    expect(getByTestId("revisao-empty-success")).toBeTruthy();
    expect(getByText("Fila de revisão vazia — tudo certo!")).toBeTruthy();
  });

  it("renders every candidate with its masked CPF, and each group's chave masked too", async () => {
    mockUseRevisaoFila.mockReturnValue(pagina([]));
    mockUseRevisaoCpfFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { items: [cpfGrupo()], total: 1, page: 1, pages: 1 },
      refetch: vi.fn(),
    });
    const { getByTestId, getAllByText, fireEvent } = {
      ...(await renderPage()),
      fireEvent: (await import("@testing-library/react")).fireEvent,
    };
    fireEvent.click(getByTestId("revisao-tab-cpf"));

    // 12345678901 → ***.***.*89-01 (owner's own example shape).
    expect(getAllByText("***.***.*89-01").length).toBeGreaterThan(0);
  });

  it("requires confirming before calling merge, and sends the selected survivor", async () => {
    mockUseRevisaoFila.mockReturnValue(pagina([]));
    mockUseRevisaoCpfFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { items: [cpfGrupo()], total: 1, page: 1, pages: 1 },
      refetch: vi.fn(),
    });
    const { getByTestId, getAllByTestId } = await renderPage(["/clientes/revisao?tab=cpf"]);
    const { fireEvent } = await import("@testing-library/react");

    // Pick the second candidate as survivor.
    const radios = getAllByTestId("cpf-candidato-sobrevivente-radio");
    fireEvent.click(radios[1]);

    fireEvent.click(getByTestId("cpf-mesclar-btn"));
    // Clicking "Mesma pessoa — unificar" opens the confirm dialog — never
    // window.confirm, and never fires the mutation on the first click.
    expect(mockCpfMerge.mutate).not.toHaveBeenCalled();
    expect(getByTestId("cpf-merge-confirm")).toBeTruthy();

    fireEvent.click(getByTestId("cpf-merge-confirm"));
    expect(mockCpfMerge.mutate).toHaveBeenCalledWith(
      { grupoId: "12345678901", clienteIdSobrevivente: "cli2" },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it("calls manterSeparados.mutate with the group's chave and filters it out on success", async () => {
    mockUseRevisaoFila.mockReturnValue(pagina([]));
    mockUseRevisaoCpfFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { items: [cpfGrupo()], total: 1, page: 1, pages: 1 },
      refetch: vi.fn(),
    });
    mockCpfManterSeparados.mutate.mockImplementation((_grupoId: string, opts: any) => {
      opts?.onSuccess?.();
    });
    const { getByTestId, queryByTestId } = await renderPage(["/clientes/revisao?tab=cpf"]);
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("cpf-manter-separados-btn"));

    expect(mockCpfManterSeparados.mutate).toHaveBeenCalledWith(
      "12345678901",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(queryByTestId("revisao-cpf-grupo-card")).toBeNull();
  });

  it("J/K/M/S shortcuts stay scoped to the Identidade tab (never fire CPF merge)", async () => {
    mockUseRevisaoFila.mockReturnValue(pagina([grupo()]));
    mockUseRevisaoCpfFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { items: [cpfGrupo()], total: 1, page: 1, pages: 1 },
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderPage(["/clientes/revisao?tab=cpf"]);
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.keyDown(window, { key: "m" });

    expect(mockMerge.mutate).not.toHaveBeenCalled();
    expect(mockCpfMerge.mutate).not.toHaveBeenCalled();
  });
});

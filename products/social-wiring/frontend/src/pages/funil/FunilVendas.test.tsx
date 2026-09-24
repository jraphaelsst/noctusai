/**
 * FunilVendas — the card the board opens.
 *
 * This suite exists because the gap it guards shipped to production: the
 * Trello-grade card was built and mounted on `/clientes`, while `/funil` —
 * the board people actually work in — still opened the old read-only field
 * list. Every unit test passed and the feature was unreachable where it
 * mattered. "Route exists" was true; "wired" was not.
 *
 * So these assert the WIRING, not the rendering: which dialog a click opens,
 * and that a card whose person layer has not resolved yet still opens
 * something rather than nothing.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockClienteDetailModal = vi.fn();
const mockLeadDetailModal = vi.fn();

vi.mock("@/components/ClienteDetailModal", () => ({
  ClienteDetailModal: (props: any) => {
    mockClienteDetailModal(props);
    return props.open ? <div data-testid="cliente-card-dialog" /> : null;
  },
}));

vi.mock("@/components/LeadDetailModal", () => ({
  LeadDetailModal: (props: any) => {
    mockLeadDetailModal(props);
    return props.open ? <div data-testid="lead-detail-modal" /> : null;
  },
}));

// The board organ, stubbed to a plain list so the test drives `onCardClick`
// directly — jsdom has no layout, so dnd-kit's real board cannot be exercised
// here and pretending otherwise would be a false green.
const ATENDIMENTOS: any[] = [];
// Partial mock: the module also exports auth/layout pieces the app shell
// pulls in. Replacing the whole module would break imports that have nothing
// to do with this test.
// Bug 5 — records every `filtros` this page hands the board, so a test can
// assert on the DEBOUNCED value the board actually queries with, not just
// the input's own (immediate) display value.
const mockFiltros = vi.fn();

vi.mock("@noctusai/lib/components", async (importOriginal) => ({
  ...(await importOriginal<any>()),
  // `toolbar` IS rendered here — the real board renders it whenever the prop
  // is set, and the page's "Novo lead" button lives in it. A stub that
  // dropped it would hide the button from every test that looks for it.
  PipelineBoard: ({ onCardClick, toolbar, filtros }: any) => {
    mockFiltros(filtros);
    return (
      <div>
        {toolbar}
        {ATENDIMENTOS.map((a) => (
          <button key={a.id} data-testid={`card-${a.id}`} onClick={() => onCardClick(a)}>
            {a.titulo}
          </button>
        ))}
      </div>
    );
  },
}));

vi.mock("@/hooks/usePipelineSeam", () => ({
  useAceitarProposta: () => ({ mutate: vi.fn(), isPending: false, variables: undefined }),
}));

// The board organ is stubbed above, so the hooks object is never called —
// it only has to exist as a prop.
vi.mock("@/lib/pipelines", () => ({ funilPipeline: {} }));

// "Novo lead" creates a LEAD through the shared mutation — never a card. The
// spy lets the suite assert exactly that: the payload goes to the lead
// endpoint's mutation and nothing on this page inserts a card.
const mockCreateLead = vi.fn();
vi.mock("@/hooks/useLeads", () => ({
  useLeadMutations: () => ({
    create: { mutate: mockCreateLead, isPending: false },
  }),
}));

// The real dialog pulls the sources + corretores dimensions over the network;
// this suite is about WIRING, so it is stubbed to expose just the submit path.
vi.mock("@/pages/leads/components/LeadFormDialog", () => ({
  LeadFormDialog: (props: any) =>
    props.open ? (
      <div data-testid="lead-form-dialog">
        <button
          data-testid="lead-form-submit"
          onClick={() => props.onSubmit({ data_entrada: "2026-09-02", origem_id: "src-zap" })}
        />
      </div>
    ) : null,
}));

async function renderFunil() {
  const { default: FunilVendas } = await import("./FunilVendas");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  // The page now runs a mutation hook, so it needs a query client in scope —
  // rendering it bare threw "No QueryClient set".
  const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    ...rtl.render(
      React.createElement(QueryClientProvider, { client: qc }, React.createElement(FunilVendas)),
    ),
    fireEvent: rtl.fireEvent,
  };
}

beforeEach(() => {
  mockClienteDetailModal.mockReset();
  mockLeadDetailModal.mockReset();
  mockCreateLead.mockReset();
  mockFiltros.mockReset();
  ATENDIMENTOS.length = 0;
});

describe("FunilVendas — Novo lead", () => {
  it("opens the shared lead form, closed until the button is pressed", async () => {
    const { fireEvent, getByTestId, queryByTestId } = await renderFunil();

    expect(queryByTestId("lead-form-dialog")).toBeNull();
    fireEvent.click(getByTestId("funil-btn-novo-lead"));
    expect(getByTestId("lead-form-dialog")).toBeTruthy();
  });

  it("creates a LEAD — never a card — and carries the chosen portal", async () => {
    // The rule this page was built on: a card exists only because migration
    // 034's trigger made one. The button must therefore go through the lead
    // mutation, exactly like a campaign lead does. `origem_id` is the portal.
    const { fireEvent, getByTestId } = await renderFunil();

    fireEvent.click(getByTestId("funil-btn-novo-lead"));
    fireEvent.click(getByTestId("lead-form-submit"));

    expect(mockCreateLead).toHaveBeenCalledTimes(1);
    expect(mockCreateLead.mock.calls[0][0]).toMatchObject({
      data_entrada: "2026-09-02",
      origem_id: "src-zap",
    });
  });
});

describe("FunilVendas — clicking a card opens the CARD", () => {
  it("opens the cliente card dialog, keyed by cliente_id", async () => {
    ATENDIMENTOS.push({ id: "a1", titulo: "Ana", cliente_id: "cli-1", lead_id: "l1" });
    const { fireEvent, getByTestId, queryByTestId } = await renderFunil();

    fireEvent.click(getByTestId("card-a1"));

    expect(getByTestId("cliente-card-dialog")).toBeTruthy();
    expect(queryByTestId("lead-detail-modal")).toBeNull();
    const calls = mockClienteDetailModal.mock.calls;
    const last = calls[calls.length - 1][0];
    expect(last.clienteId).toBe("cli-1");
    expect(last.open).toBe(true);
    // The Funil is the one board that opens the card WITH an atendimento in
    // context — this is what gates `ClienteCardDialog`'s "Arquivar" icon.
    expect(last.atendimentoId).toBe("a1");
  });

  it("clears BOTH clienteId and atendimentoId on close, together", async () => {
    ATENDIMENTOS.push({ id: "a4", titulo: "Ana", cliente_id: "cli-4", lead_id: "l4" });
    const { act } = await import("@testing-library/react");
    const { fireEvent, getByTestId } = await renderFunil();

    fireEvent.click(getByTestId("card-a4"));
    const beforeClose = mockClienteDetailModal.mock.calls;
    expect(beforeClose[beforeClose.length - 1][0].atendimentoId).toBe("a4");

    await act(async () => {
      beforeClose[beforeClose.length - 1][0].onClose();
    });

    const afterClose = mockClienteDetailModal.mock.calls;
    const last = afterClose[afterClose.length - 1][0];
    expect(last.clienteId).toBeNull();
    expect(last.atendimentoId).toBeNull();
    expect(last.open).toBe(false);
  });

  it("falls back to the lead detail when the person layer has not resolved", async () => {
    // `cliente_id` is null between a lead landing and the 6-hourly backfill
    // attaching it. Opening nothing would be a dead click on a real card.
    ATENDIMENTOS.push({ id: "a2", titulo: "Sem cliente", cliente_id: null, lead_id: "l2" });
    const { fireEvent, getByTestId, queryByTestId } = await renderFunil();

    fireEvent.click(getByTestId("card-a2"));

    expect(getByTestId("lead-detail-modal")).toBeTruthy();
    expect(queryByTestId("cliente-card-dialog")).toBeNull();
  });

  it("opens nothing before any card is clicked", async () => {
    ATENDIMENTOS.push({ id: "a3", titulo: "Ana", cliente_id: "cli-3" });
    const { queryByTestId } = await renderFunil();

    expect(queryByTestId("cliente-card-dialog")).toBeNull();
    expect(queryByTestId("lead-detail-modal")).toBeNull();
  });
});

describe("FunilVendas — Bug 5 (prod card 755253934): a debounced search, not one GET per keystroke", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("🔴 does NOT hand the board a fresh `filtros.busca` on every keystroke", async () => {
    const { act } = await import("@testing-library/react");
    const { fireEvent, getByPlaceholderText } = await renderFunil();
    const input = getByPlaceholderText(
      "Buscar por nome, contato ou empreendimento...",
    ) as HTMLInputElement;

    mockFiltros.mockClear();
    act(() => {
      fireEvent.change(input, { target: { value: "A" } });
    });
    act(() => {
      fireEvent.change(input, { target: { value: "AN" } });
    });
    act(() => {
      fireEvent.change(input, { target: { value: "ANA" } });
    });

    // Three keystrokes, three re-renders (React state updates on every
    // change) — but every one of them must still carry the PRE-typing
    // `busca` (`undefined`) into `filtros`, because the debounced value has
    // not settled yet. The old code handed the board a fresh non-empty
    // `busca` on the FIRST keystroke already.
    for (const call of mockFiltros.mock.calls) {
      expect(call[0].busca).toBeUndefined();
    }

    // `act` flushes the effect the debounce's `setTimeout` schedules AND the
    // resulting state update in the same synchronous pass — no `waitFor`
    // polling needed (and polling against fake timers is exactly the kind
    // of mismatch that flakes under load).
    act(() => {
      vi.advanceTimersByTime(300);
    });

    const calls = mockFiltros.mock.calls;
    const last = calls[calls.length - 1]?.[0];
    expect(last?.busca).toBe("ANA");
  });

  it("the input itself stays IMMEDIATE — typing is never visibly delayed", async () => {
    const { fireEvent, getByPlaceholderText } = await renderFunil();
    const input = getByPlaceholderText(
      "Buscar por nome, contato ou empreendimento...",
    ) as HTMLInputElement;

    fireEvent.change(input, { target: { value: "Ana" } });
    expect(input.value).toBe("Ana");
  });
});

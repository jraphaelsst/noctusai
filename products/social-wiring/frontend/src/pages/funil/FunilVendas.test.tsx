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
vi.mock("@noctusai/lib/components", async (importOriginal) => ({
  ...(await importOriginal<any>()),
  PipelineBoard: ({ onCardClick }: any) => (
    <div>
      {ATENDIMENTOS.map((a) => (
        <button key={a.id} data-testid={`card-${a.id}`} onClick={() => onCardClick(a)}>
          {a.titulo}
        </button>
      ))}
    </div>
  ),
}));

vi.mock("@/hooks/usePipelineSeam", () => ({
  useAceitarProposta: () => ({ mutate: vi.fn(), isPending: false, variables: undefined }),
}));

// The board organ is stubbed above, so the hooks object is never called —
// it only has to exist as a prop.
vi.mock("@/lib/pipelines", () => ({ funilPipeline: {} }));

async function renderFunil() {
  const { default: FunilVendas } = await import("./FunilVendas");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(FunilVendas)), fireEvent: rtl.fireEvent };
}

beforeEach(() => {
  mockClienteDetailModal.mockReset();
  mockLeadDetailModal.mockReset();
  ATENDIMENTOS.length = 0;
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

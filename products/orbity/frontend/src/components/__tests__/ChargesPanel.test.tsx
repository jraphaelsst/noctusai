/**
 * ChargesPanel -- the month summary + every receivable with its gateway status banner.
 *
 * Loading honesty (KB lying-loading-state): the skeleton shows only while there is NO data (`isPending && !data`); a
 * background refetch keeps the rows on screen and shows "Atualizando…" instead; an empty list is only claimed when the
 * request really answered empty.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import type { Charge } from "@/hooks/useFinancial";

const m = vi.hoisted(() => ({
  cashFlow: vi.fn(), charges: vi.fn(), gateway: vi.fn(), requeue: vi.fn(), create: vi.fn(), clients: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return { api, supabase: {}, appConfig: {}, useAuthStore: () => ({ user: null }), default: { api } };
});
vi.mock("@/hooks/useFinancial", () => ({
  useCashFlow: () => m.cashFlow(),
  useCharges: (f: unknown) => m.charges(f),
  useGatewayStatus: () => m.gateway(),
  useRequeueCharge: () => m.requeue(),
  useCreateExtraCharge: () => m.create(),
}));
vi.mock("@/hooks/useClients", () => ({ useClientOptions: () => m.clients(), useLeadOptions: () => m.clients() }));

import { ChargesPanel } from "../ChargesPanel";

const q = (o: object) => ({ data: undefined, isPending: false, isFetching: false, isError: false, error: null, refetch: vi.fn(), ...o });
const CASH = { reference_month: "2026-10-01", paid_revenues: 1000, pending_revenues: 300, overdue_revenues: 500, paid_expenses: 300, net: 700 };

function charge(over: Partial<Charge> = {}): Charge {
  return {
    entry_id: "e1", client_id: "c1", client_name: "Acme LTDA", contract_id: null, description: "Gestão — 10/2026", due_date: "2026-10-20",
    amount_cents: 150000, settled_cents: 0, entry_status: "open", overdue: false, generation_status: "generated", generation_attempts: 1,
    last_error: null, next_attempt_at: null, gateway: "asaas", billing_method: "boleto", external_id: "pay_1",
    invoice_url: "https://asaas.test/i/1", pix_payload: null, preserved_after_deactivation: false, gateway_cancel_status: null,
    gateway_cancel_error: null, ...over,
  };
}
const list = (items: Charge[]) => ({ items, total: items.length, page: 1, page_size: 25 });

beforeEach(() => {
  vi.clearAllMocks();
  m.cashFlow.mockReturnValue(q({ data: CASH }));
  m.gateway.mockReturnValue(q({ data: { gateway: "asaas", configured: true } }));
  m.requeue.mockReturnValue({ mutate: vi.fn(), isPending: false });
  m.create.mockReturnValue({ mutate: vi.fn(), isPending: false });
  m.clients.mockReturnValue(q({ data: [] }));
});

describe("ChargesPanel", () => {
  it("shows the month summary", () => {
    m.charges.mockReturnValue(q({ data: list([]) }));
    render(<ChargesPanel isAdmin />);
    expect(screen.getByText("Recebido")).toBeInTheDocument();
    expect(screen.getByText(/1\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/Em atraso/)).toBeInTheDocument();
  });

  it("renders a skeleton ONLY while there is no data yet", () => {
    m.charges.mockReturnValue(q({ isPending: true, isFetching: true }));
    m.cashFlow.mockReturnValue(q({ isPending: true, isFetching: true }));
    render(<ChargesPanel isAdmin />);
    expect(screen.queryByText(/Nenhuma cobrança/)).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("Carregando").length).toBeGreaterThan(0);
    expect(screen.queryByText("Acme LTDA")).not.toBeInTheDocument();
  });

  it("a background refetch keeps the rows and only says 'Atualizando…' (never the empty message over data)", () => {
    m.charges.mockReturnValue(q({ data: list([charge()]), isFetching: true }));
    render(<ChargesPanel isAdmin />);
    expect(screen.getByText("Acme LTDA")).toBeInTheDocument();
    expect(screen.getAllByText("Atualizando…").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Nenhuma cobrança/)).not.toBeInTheDocument();
  });

  it("says the list is empty only when the request answered empty", () => {
    m.charges.mockReturnValue(q({ data: list([]) }));
    render(<ChargesPanel isAdmin />);
    expect(screen.getByText(/Nenhuma cobrança ainda/)).toBeInTheDocument();
  });

  it("surfaces a failed load with a retry", () => {
    const refetch = vi.fn();
    m.charges.mockReturnValue(q({ isError: true, error: new Error("502"), refetch }));
    render(<ChargesPanel isAdmin />);
    fireEvent.click(screen.getAllByRole("button", { name: "Tentar novamente" })[0]);
    expect(refetch).toHaveBeenCalled();
  });

  it("each charge carries its own status banner (queued/retrying/failed/skipped) with the last error", () => {
    m.charges.mockReturnValue(q({
      data: list([
        charge({ entry_id: "q", generation_status: "queued", external_id: null, invoice_url: null }),
        charge({ entry_id: "r", generation_status: "retrying", generation_attempts: 2, last_error: "timeout calling /payments", external_id: null }),
        charge({ entry_id: "f", generation_status: "failed", last_error: "Cliente sem CPF/CNPJ", external_id: null }),
        charge({ entry_id: "s", generation_status: "skipped", last_error: "Gateway de cobrança não configurado para esta organização.", external_id: null }),
        charge({ entry_id: "g" }),
      ]),
    }));
    render(<ChargesPanel isAdmin />);
    expect(screen.getByTestId("charge-banner-q")).toHaveAttribute("data-status", "queued");
    expect(within(screen.getByTestId("charge-banner-r")).getByText(/timeout calling/)).toBeInTheDocument();
    expect(within(screen.getByTestId("charge-banner-f")).getByText("Cliente sem CPF/CNPJ")).toBeInTheDocument();
    expect(within(screen.getByTestId("charge-banner-s")).getByText(/não configurado/)).toBeInTheDocument();
    expect(within(screen.getByTestId("charge-banner-g")).getByRole("link", { name: "Abrir fatura" })).toHaveAttribute("href", "https://asaas.test/i/1");
  });

  it("an admin can re-queue a failed charge; staff cannot", () => {
    const mutate = vi.fn();
    m.requeue.mockReturnValue({ mutate, isPending: false });
    m.charges.mockReturnValue(q({ data: list([charge({ generation_status: "failed", last_error: "x", external_id: null })]) }));
    const { unmount } = render(<ChargesPanel isAdmin />);
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(mutate).toHaveBeenCalledWith("e1");
    unmount();
    render(<ChargesPanel isAdmin={false} />);
    expect(screen.queryByRole("button", { name: "Tentar novamente" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nova cobrança avulsa" })).not.toBeInTheDocument();
  });

  it("flags a kept charge and a pending gateway cancel", () => {
    m.charges.mockReturnValue(q({ data: list([charge({ preserved_after_deactivation: true, gateway_cancel_status: "failed", gateway_cancel_error: "A cobrança já foi paga no gateway" })]) }));
    render(<ChargesPanel isAdmin />);
    expect(screen.getByText(/Mantida após a inativação/)).toBeInTheDocument();
    expect(screen.getByText(/Não foi possível cancelar no gateway/)).toBeInTheDocument();
  });

  it("warns when no gateway is configured (charges stay plain receivables)", () => {
    m.gateway.mockReturnValue(q({ data: { gateway: "asaas", configured: false } }));
    m.charges.mockReturnValue(q({ data: list([]) }));
    render(<ChargesPanel isAdmin />);
    expect(screen.getByText(/Nenhum gateway de cobrança configurado/)).toBeInTheDocument();
  });

  it("filters by gateway status", () => {
    m.charges.mockReturnValue(q({ data: list([]) }));
    render(<ChargesPanel isAdmin />);
    fireEvent.change(screen.getByLabelText("Filtrar por status do gateway"), { target: { value: "failed" } });
    expect(m.charges).toHaveBeenLastCalledWith(expect.objectContaining({ generation_status: "failed", page: 1 }));
  });
});

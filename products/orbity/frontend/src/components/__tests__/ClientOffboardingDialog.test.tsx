/**
 * ClientOffboardingDialog -- every open charge gets a decision (cancel by default), a partially paid one can only be kept,
 * the final action asks the seed useConfirm dialog (never window.confirm) and posts ONE operation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom";
import { ConfirmProvider } from "@noctusai/lib/components";

const { mockGet, mockPost, toast } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn(), toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: mockPost } }));
vi.mock("@noctusai/seed/infra", () => ({ api: {}, useAuthStore: () => ({ user: null }), default: { api: {} } }));
vi.mock("sonner", () => ({ toast }));

import { ClientOffboardingDialog, decisionsPayload, defaultDecisions, summaryMessage, type OffboardingPreview } from "../ClientOffboardingDialog";

const PREVIEW: OffboardingPreview = {
  client: { id: "c1", name: "Acme LTDA", active: true },
  charges: [
    { entry_id: "e1", description: "Gestão — 09/2026", due_date: "2026-09-20", amount_cents: 150000, entry_status: "open", overdue: true, generation_status: "generated", external_id: "pay_1" },
    { entry_id: "e2", description: "Gestão — 10/2026", due_date: "2026-10-20", amount_cents: 150000, entry_status: "partial", overdue: false, generation_status: "skipped", external_id: null },
  ],
  contracts: [{ id: "k1", title: "Gestão de tráfego", status: "active" }],
};

function renderDialog(onDone = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConfirmProvider>
        <ClientOffboardingDialog clientId="c1" open onClose={vi.fn()} onDone={onDone} />
      </ConfirmProvider>
    </QueryClientProvider>,
  );
  return onDone;
}

let nativeConfirm: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue(PREVIEW);
  nativeConfirm = vi.fn();
  vi.stubGlobal("confirm", nativeConfirm);
});
afterEach(() => vi.unstubAllGlobals());

describe("decisions", () => {
  it("defaults to cancel, except a partially paid charge which can only be kept", () => {
    expect(defaultDecisions(PREVIEW.charges)).toEqual({ e1: "cancel", e2: "keep" });
  });
  it("posts one decision per charge", () => {
    expect(decisionsPayload({ e1: "cancel", e2: "keep" })).toEqual({ charges: [{ entry_id: "e1", action: "cancel" }, { entry_id: "e2", action: "keep" }] });
  });
  it("summarises what happened, including a gateway cancel still pending", () => {
    expect(summaryMessage({ cancelled: 1, preserved: 1, contracts_terminated: ["k1"], gateway_pending: 2 })).toBe(
      "1 cobrança(s) cancelada(s) · 1 mantida(s) · 1 contrato(s) encerrado(s) · 2 cancelamento(s) no gateway pendente(s)",
    );
  });
});

describe("ClientOffboardingDialog", () => {
  it("lists the open charges with cancel preselected, and the contracts that will end", async () => {
    renderDialog();
    const list = await screen.findByRole("list", { name: "Cobranças em aberto" });
    const first = within(list).getAllByRole("listitem")[0];
    expect(within(first).getByRole("radio", { name: "Cancelar" })).toBeChecked();
    expect(within(first).getByText(/atrasada/)).toBeInTheDocument();
    expect(within(first).getByText(/com cobrança no gateway/)).toBeInTheDocument();
    const second = within(list).getAllByRole("listitem")[1];
    expect(within(second).getByRole("radio", { name: "Cancelar" })).toBeDisabled();
    expect(within(second).getByRole("radio", { name: "Manter" })).toBeChecked();
    expect(screen.getByText("Gestão de tráfego")).toBeInTheDocument();
  });

  it("asks the seed confirm dialog (never window.confirm), then posts ONE operation with the operator's choices", async () => {
    mockPost.mockResolvedValue({ ok: true, cancelled: 0, preserved: 2, contracts_terminated: ["k1"], contracts_failed: [], gateway_cancelled: 0, gateway_pending: 0 });
    const onDone = renderDialog();
    const list = await screen.findByRole("list", { name: "Cobranças em aberto" });
    fireEvent.click(within(within(list).getAllByRole("listitem")[0]).getByRole("radio", { name: "Manter" }));
    fireEvent.click(screen.getByRole("button", { name: "Inativar cliente" }));
    fireEvent.click(within(await screen.findByTestId("confirm-dialog")).getByRole("button", { name: "Inativar cliente" }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    expect(mockPost).toHaveBeenCalledWith("/api/clients/c1/archive", { charges: [{ entry_id: "e1", action: "keep" }, { entry_id: "e2", action: "keep" }] });
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("does nothing when the operator declines the confirmation", async () => {
    renderDialog();
    await screen.findByRole("list", { name: "Cobranças em aberto" });
    fireEvent.click(screen.getByRole("button", { name: "Inativar cliente" }));
    fireEvent.click(within(await screen.findByTestId("confirm-dialog")).getByRole("button", { name: "Cancelar" }));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("a client with no open charges still goes through the dialog (contracts end)", async () => {
    mockGet.mockResolvedValue({ ...PREVIEW, charges: [] });
    renderDialog();
    expect(await screen.findByText(/não tem cobranças em aberto/)).toBeInTheDocument();
  });

  it("a failed load is reported with a retry, not an empty list", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    renderDialog();
    expect(await screen.findByText(/Erro ao carregar as cobranças do cliente/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("a refused operation is shown to the operator and the dialog stays open", async () => {
    mockPost.mockRejectedValue(new Error("Decida o destino de todas as cobranças em aberto do cliente."));
    const onDone = renderDialog();
    await screen.findByRole("list", { name: "Cobranças em aberto" });
    fireEvent.click(screen.getByRole("button", { name: "Inativar cliente" }));
    fireEvent.click(within(await screen.findByTestId("confirm-dialog")).getByRole("button", { name: "Inativar cliente" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(onDone).not.toHaveBeenCalled();
  });
});

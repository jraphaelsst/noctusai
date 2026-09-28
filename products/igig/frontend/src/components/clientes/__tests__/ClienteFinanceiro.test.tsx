/**
 * ClienteFinanceiro — the Clientes card's "Financeiro" tab.
 *
 * Tech-lead addendum: "Paga" is a money-movement action, same as the
 * Financeiro page's own button — it must be admin-only AND behind a
 * confirmation dialog, not a bare one-click mutate.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

const mockUseFaturas = vi.fn();
const mockMarcarPaga = { mutate: vi.fn(), isPending: false };
const mockIsOrgAdmin = vi.fn(() => true);

vi.mock("@/hooks/useFinanceiro", () => ({
  useFaturas: () => mockUseFaturas(),
  useMarcarPaga: () => mockMarcarPaga,
}));

vi.mock("@/lib/useIsOrgAdmin", () => ({
  useIsOrgAdmin: () => mockIsOrgAdmin(),
}));

import { ClienteFinanceiro } from "../ClienteFinanceiro";

const FATURA_ABERTA = {
  id: "f1", cliente_id: "c1", contrato_id: null, competencia: "2026-08",
  valor_total: 500, vencimento: "2026-08-10", status: "aberta" as const,
  pago_em: null, enviada_em: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockIsOrgAdmin.mockReturnValue(true);
  mockMarcarPaga.isPending = false;
  mockUseFaturas.mockReturnValue({
    faturas: [FATURA_ABERTA], loading: false, isError: false, error: null,
  });
});

describe("ClienteFinanceiro — 'Paga' is admin-only and confirmed", () => {
  it("shows the Paga button to an admin", () => {
    render(<ClienteFinanceiro clienteId="c1" />);
    expect(screen.getByRole("button", { name: /paga/i })).toBeInTheDocument();
  });

  it("hides the Paga button from a non-admin", () => {
    mockIsOrgAdmin.mockReturnValue(false);
    render(<ClienteFinanceiro clienteId="c1" />);
    expect(screen.queryByRole("button", { name: /paga/i })).not.toBeInTheDocument();
  });

  it("does NOT mutate on click alone — opens a confirmation first", () => {
    render(<ClienteFinanceiro clienteId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: /paga/i }));
    expect(mockMarcarPaga.mutate).not.toHaveBeenCalled();
    expect(screen.getByText(/não há como desfazer pela tela/i)).toBeInTheDocument();
  });

  it("mutates only after the confirmation is confirmed", () => {
    render(<ClienteFinanceiro clienteId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: /paga/i }));
    fireEvent.click(screen.getByRole("button", { name: "Marcar paga" }));
    expect(mockMarcarPaga.mutate).toHaveBeenCalledWith("f1", expect.anything());
  });
});

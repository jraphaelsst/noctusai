/**
 * ClienteDadosPanel — "Remover cliente" mirrors the backend's admin-only
 * DELETE (`exigir_admin_da_org`): shown to an org admin, hidden from a member.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockIsOrgAdmin = vi.fn(() => true);
vi.mock("@/lib/useIsOrgAdmin", () => ({ useIsOrgAdmin: () => mockIsOrgAdmin() }));
vi.mock("@/hooks/useClientes", () => ({
  useAtivarCliente: () => ({ mutate: vi.fn(), isPending: false }),
  useAtualizarCliente: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  useRemoverCliente: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { ClienteDadosPanel } from "../ClienteDadosPanel";

const CLIENTE = {
  id: "c1", org_id: "org", nome: "Padaria Sol", nicho: null, email: null, telefone: null,
  status: "ativo", origem: null, observacoes: null, created_at: "2026-09-01T10:00:00Z", updated_at: null,
} as never;

function renderPanel() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ClienteDadosPanel cliente={CLIENTE} onRemovido={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => mockIsOrgAdmin.mockReturnValue(true));
afterEach(cleanup);

describe("ClienteDadosPanel — Remover cliente is admin-only", () => {
  it("shows the button to an admin", () => {
    renderPanel();
    expect(screen.getByTestId("cliente-remover")).toBeInTheDocument();
  });

  it("hides the button from a non-admin", () => {
    mockIsOrgAdmin.mockReturnValue(false);
    renderPanel();
    expect(screen.queryByTestId("cliente-remover")).not.toBeInTheDocument();
  });
});

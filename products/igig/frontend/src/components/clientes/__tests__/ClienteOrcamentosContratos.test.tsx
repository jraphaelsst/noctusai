/**
 * Contratos — admin edit + encerrar (never delete); empty-state actions.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const { api, admin } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  admin: { value: true },
}));
vi.mock("@noctusai/seed/infra", () => ({ api, useAuthStore: () => ({ user: { id: "u1", user_metadata: {} } }) }));
vi.mock("@/lib/useIsOrgAdmin", () => ({ useIsOrgAdmin: () => admin.value }));

import { ClienteOrcamentosContratos } from "../ClienteOrcamentosContratos";

const BASE = {
  id: "k1", cliente_id: "c1", orcamento_id: "o1", numero: "2026-001", valor_mensal: 1500, posts_por_mes: 12,
  valor_excedente: 80, dia_vencimento: 10, data_inicio: null, data_fim: null, data_encerramento: null,
  motivo_encerramento: null, status: "ativo", modalidade_assinatura: "fisica", assinado_em: null,
  assinado_manual_em: null, documento_key: null, documento_assinado_key: null, link_assinatura: null,
  created_at: "2026-09-20T10:00:00Z",
};

function mount(contratos: unknown[]) {
  api.get.mockImplementation(async (path: string) => {
    if (path === "/api/contratos") return { data: contratos };
    if (path === "/api/orcamentos") return { data: [] };
    throw new Error(`GET inesperado ${path}`);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ClienteOrcamentosContratos clienteId="c1" onAbrirOrcamento={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  admin.value = true;
  api.post.mockResolvedValue({ data: { ...BASE, status: "encerrado" } });
  api.patch.mockResolvedValue({ data: BASE });
});
afterEach(cleanup);

describe("Contratos — editar / encerrar", () => {
  it("admin encerra com motivo + data", async () => {
    mount([BASE]);
    fireEvent.click(await screen.findByTestId("contrato-encerrar"));
    const confirmar = await screen.findByTestId("contrato-confirmar-encerrar");
    expect(confirmar).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Cliente saiu" } });
    fireEvent.click(confirmar);
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, corpo] = api.post.mock.calls[0];
    expect(path).toBe("/api/contratos/k1/encerrar");
    expect(corpo.motivo).toBe("Cliente saiu");
    expect(corpo.data_encerramento).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("admin edita o valor mensal", async () => {
    mount([BASE]);
    fireEvent.click(await screen.findByTestId("contrato-editar"));
    fireEvent.change(await screen.findByLabelText("Valor mensal (R$)"), { target: { value: "2000" } });
    fireEvent.click(screen.getByTestId("contrato-salvar"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch.mock.calls[0][0]).toBe("/api/contratos/k1");
    expect(api.patch.mock.calls[0][1].valor_mensal).toBe(2000);
  });

  it("não-admin não vê editar/encerrar", async () => {
    admin.value = false;
    mount([BASE]);
    await screen.findByTestId("contrato-k1");
    expect(screen.queryByTestId("contrato-editar")).toBeNull();
    expect(screen.queryByTestId("contrato-encerrar")).toBeNull();
  });

  it("encerrado aparece com data e sem ações", async () => {
    mount([{ ...BASE, status: "encerrado", data_encerramento: "2026-02-10", motivo_encerramento: "Fim" }]);
    expect(await screen.findByText(/encerrado em/)).toBeInTheDocument();
    expect(screen.getByText("Motivo: Fim")).toBeInTheDocument();
    expect(screen.queryByTestId("contrato-editar")).toBeNull();
  });

  it("estados vazios têm ação real", async () => {
    mount([]);
    expect(await screen.findByRole("link", { name: "Ver orçamentos" })).toHaveAttribute("href", "/orcamentos");
    expect(await screen.findByRole("link", { name: "Ir para o Comercial" })).toHaveAttribute("href", "/comercial");
  });
});

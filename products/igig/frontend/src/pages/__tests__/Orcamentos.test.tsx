/**
 * Orçamentos page: tabs → server `aba`, cards with the four states, and the
 * `?id=` deep link (the reply-watcher notification's target) opening the modal.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import Orcamentos, { noPeriodo } from "../Orcamentos";

const ORC = {
  id: "o1", negocio_id: "n1", lead_id: "l1", cliente_id: null, versao: 1, titulo: "Social mensal", status: "enviado",
  validade: null, itens: [], limites_escopo: { revisoes_incluidas: 2, valor_excedente: 0 }, observacoes: null,
  pdf_key: null, enviado_em: null, respondido_em: null, aceito_em: null, recusado_em: null, motivo_recusa: null,
  created_at: "2026-09-20T10:00:00Z", lead: { id: "l1", nome: "Ana", email: null, empresa: "Padaria Ana" },
  negocio: { id: "n1", titulo: "Padaria", etapa_id: "s1", status: "aberto" },
  subtotal_criacao: 1000, subtotal_gestao: 500, desconto: 0, total_mensal: 1500, custo_estimado: 600,
  margem_estimada: 60, horas_estimadas: 10,
};

function renderPage(url = "/orcamentos") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <Orcamentos />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
    if (path === "/api/orcamentos") return { data: params?.aba === "aceitos" ? [] : [ORC] };
    if (path === "/api/orcamentos/o1") return { data: ORC };
    if (path === "/api/orcamentos/o1/emails") return { data: [] };
    if (path === "/api/comercial/leads") return [];
    if (path === "/api/produtos-servicos") return { data: [] };
    throw new Error(`GET inesperado ${path}`);
  });
  api.post.mockResolvedValue({ data: { ...ORC, itens: [] } });
});
afterEach(cleanup);

describe("Orçamentos page", () => {
  it("lists the Ativos tab by default and switches tabs through the server's `aba`", async () => {
    renderPage();
    expect(await screen.findByText("Padaria Ana")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/api/orcamentos", { aba: "ativos" });
    fireEvent.click(screen.getByRole("tab", { name: "Aceitos" }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/orcamentos", { aba: "aceitos" }));
    expect(await screen.findByText("Nenhum orçamento aceito ainda.")).toBeInTheDocument();
  });

  it("shows the server's error instead of an empty list", async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/orcamentos") throw new Error("banco indisponível");
      return [];
    });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("banco indisponível");
  });

  it("?id= deep link opens the orçamento modal", async () => {
    renderPage("/orcamentos?id=o1");
    expect(await screen.findByTestId("orcamento-modal")).toBeInTheDocument();
    await waitFor(() => expect(api.get.mock.calls.some(([p]) => p === "/api/orcamentos/o1")).toBe(true));
  });

  it("period filter is inclusive on created_at's date", () => {
    expect(noPeriodo({ created_at: "2026-09-20T23:00:00Z" }, "2026-09-20", "2026-09-20")).toBe(true);
    expect(noPeriodo({ created_at: "2026-09-19T23:00:00Z" }, "2026-09-20", "")).toBe(false);
    expect(noPeriodo({ created_at: "2026-09-21T00:00:00Z" }, "", "2026-09-20")).toBe(false);
  });
});

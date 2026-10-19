import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import { PainelLeadConteudo } from "./PainelLead";

const P = (chave: string, over: Record<string, unknown> = {}) => ({
  chave, label: `Q ${chave}`, categoria: "x", operacao: null, ativa: true,
  qualificatoria: false, bloqueada: false, usada_em_criterio: false, ...over,
});

function setup(contato: unknown) {
  api.get.mockImplementation((url: string) => {
    if (url === "/api/julia/perguntas")
      return Promise.resolve({ data: { catalogo: [P("nome", { qualificatoria: true }), P("renda"), P("off", { ativa: false })], limites: { max_ativas: 8, max_qualificatorias: 5 } } });
    return contato instanceof Error ? Promise.reject(contato) : Promise.resolve({ data: contato });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><PainelLeadConteudo connectionId="c1" chatId="5511@c.us" /></QueryClientProvider>);
}

beforeEach(() => { api.get.mockReset(); });
afterEach(cleanup);

describe("PainelLead", () => {
  it("renders operação, active questions with value or dash, qualificatória marked, hides inactive", async () => {
    setup({ contato: {}, slots: { nome: "Ana", off: "x" }, interacao_atual: { operacao: "compra" } });
    expect(screen.getByTestId("painel-lead-skeleton")).toBeTruthy();
    await screen.findByTestId("painel-lead");
    expect(screen.getByTestId("painel-operacao").textContent).toContain("Compra");
    expect(screen.getByTestId("painel-slot-nome").textContent).toContain("Ana");
    expect(screen.getByTestId("painel-slot-nome").querySelector('[aria-label="Qualificatória"]')).toBeTruthy();
    expect(screen.getByTestId("painel-slot-renda").textContent).toContain("—");
    expect(screen.queryByTestId("painel-slot-off")).toBeNull();
  });

  it("shows the empty-data state when the contact is unknown", async () => {
    setup(Object.assign(new Error("404"), { status: 404 }));
    expect(await screen.findByTestId("painel-lead-erro")).toBeTruthy();
  });
});

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn() }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("sonner", () => ({ toast }));

import JuliaPerguntas from "./Perguntas";

const P = (chave: string, over: Record<string, unknown> = {}) => ({
  chave, label: `Pergunta ${chave}`, categoria: "Informações do lead", operacao: null,
  ativa: false, qualificatoria: false, bloqueada: false, usada_em_criterio: false, ...over,
});
function dados(catalogo: unknown[], limites = { max_ativas: 8, max_qualificatorias: 5 }) {
  return { data: { catalogo, limites } };
}
function erro(status: number, code: string, details?: unknown) {
  return Object.assign(new Error(`[${status}]`), { status, body: { error: { code, message: "x", details } } });
}
function setup(payload: unknown) {
  api.get.mockResolvedValue(payload);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><JuliaPerguntas /></QueryClientProvider>);
}

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); toast.error.mockReset(); toast.success.mockReset(); h.admin = true; });
afterEach(cleanup);

describe("Julia Perguntas", () => {
  it("shows skeleton then only active questions; 'Mostrar todas' reveals the rest", async () => {
    setup(dados([P("objetivo", { ativa: true, bloqueada: true }), P("nome", { ativa: true }), P("renda")]));
    expect(screen.getByTestId("perguntas-skeleton")).toBeTruthy();
    await screen.findByTestId("pergunta-nome");
    expect(screen.queryByTestId("pergunta-renda")).toBeNull();
    fireEvent.click(screen.getByTestId("perguntas-mostrar-todas"));
    expect(screen.getByTestId("pergunta-renda")).toBeTruthy();
  });

  it("locks the objective question with the essential tooltip", async () => {
    setup(dados([P("objetivo", { ativa: true, bloqueada: true })]));
    const sw = await screen.findByTestId("switch-objetivo");
    expect((sw as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("motivo-objetivo").textContent).toContain("essencial para a identificação da operação correta");
    expect(screen.getByText("Objetivo: comprar ou alugar")).toBeTruthy();
  });

  it("disables inactive switches at the active limit with the limit message", async () => {
    const ativas = Array.from({ length: 2 }, (_, i) => P(`a${i}`, { ativa: true }));
    setup(dados([...ativas, P("extra")], { max_ativas: 2, max_qualificatorias: 5 }));
    await screen.findByTestId("pergunta-a0");
    fireEvent.click(screen.getByTestId("perguntas-mostrar-todas"));
    expect((screen.getByTestId("switch-extra") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("motivo-extra").textContent).toContain("Você atingiu o limite de perguntas adicionadas");
  });

  it("blocks switching off a question used by a criterion", async () => {
    setup(dados([P("renda", { ativa: true, usada_em_criterio: true })]));
    expect((await screen.findByTestId("switch-renda") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("motivo-renda").textContent).toContain("primeiro desative os critérios de envio");
  });

  it("filters by category", async () => {
    setup(dados([P("a", { ativa: true, categoria: "Localização" }), P("b", { ativa: true })]));
    await screen.findByTestId("pergunta-a");
    fireEvent.click(screen.getByTestId("categoria-Localização"));
    expect(screen.queryByTestId("pergunta-b")).toBeNull();
    expect(screen.getByTestId("pergunta-a")).toBeTruthy();
  });

  it("saves the full selection (qualificatória) and shows 422/409 messages", async () => {
    setup(dados([P("objetivo", { ativa: true, bloqueada: true }), P("nome", { ativa: true })]));
    fireEvent.click(await screen.findByTestId("qualif-nome"));
    api.put.mockRejectedValueOnce(erro(409, "usada_em_criterio", { criterios: ["Grupo 1"] }));
    fireEvent.click(screen.getByTestId("perguntas-salvar"));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(api.put).toHaveBeenCalledWith("/api/julia/perguntas", {
      selecao: [{ chave: "objetivo", qualificatoria: false }, { chave: "nome", qualificatoria: true }],
    });
    expect(String(toast.error.mock.calls[0][0])).toContain("primeiro desative os critérios de envio");
    expect(String(toast.error.mock.calls[0][0])).toContain("Grupo 1");

    api.put.mockRejectedValueOnce(erro(422, "limite_ativas"));
    fireEvent.click(screen.getByTestId("perguntas-salvar"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(2));
    expect(String(toast.error.mock.calls[1][0])).toContain("limite de perguntas adicionadas");
  });

  it("is read-only for non-admins and shows an error state with retry", async () => {
    h.admin = false;
    setup(dados([P("nome", { ativa: true })]));
    expect(await screen.findByTestId("perguntas-somente-leitura")).toBeTruthy();
    expect(screen.queryByTestId("perguntas-salvar")).toBeNull();
    cleanup();
    api.get.mockRejectedValue(erro(500, "x"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><JuliaPerguntas /></QueryClientProvider>);
    expect(await screen.findByTestId("perguntas-erro")).toBeTruthy();
  });
});

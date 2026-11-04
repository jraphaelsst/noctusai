/**
 * Julia › Especificações do negócio, READ-ONLY: values shown as text with "Alterado por … em …", the support note, NO inputs and no
 * save, for every role; typed refusals of the read are named.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import { EspecificacoesCard, NOTA_EDICAO_NOCTUS } from "./EspecificacoesCard";
import type { Especificacoes, TipoEspecificacao } from "@/hooks/useJuliaEspecificacoes";

const decl = (chave: string, tipo: TipoEspecificacao, over: Record<string, unknown> = {}) => ({
  id: `id-${chave}`, chave, rotulo: `Rótulo ${chave}`, descricao: null, tipo, obrigatoria: false, exemplo: null, ...over,
});

const ESPEC: Especificacoes = {
  agent_key: "julia", version_id: "v1", versao: 3,
  declaradas: [decl("nome_empresa", "texto_curto", { obrigatoria: true }), decl("horario", "horario"), decl("dominios", "dominios")],
  valores: [{ chave: "nome_empresa", valor: "Lastro", updated_at: "2026-11-04T10:00:00Z", updated_by_nome: "Ana Dona" }],
  faltando: ["horario"], invalidas: [], modo_validacao: "bloquear",
};

function erro(status: number, body: unknown) {
  return Object.assign(new Error(`[${status}] x`), { status, body });
}

function setup(opts: { get?: unknown; admin?: boolean } = {}) {
  api.get.mockImplementation(() => (opts.get instanceof Error ? Promise.reject(opts.get) : Promise.resolve(opts.get ?? ESPEC)));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><EspecificacoesCard isAdmin={opts.admin ?? true} /></QueryClientProvider>);
}

beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));
afterEach(cleanup);

describe("read-only card", () => {
  it.each([true, false])("has no inputs, no textarea and no save button (isAdmin=%s)", async (admin) => {
    setup({ admin });
    await screen.findByTestId("espec-lista");
    expect(document.querySelectorAll("input, textarea, select")).toHaveLength(0);
    expect(screen.queryByTestId("espec-salvar")).toBeNull();
    expect(screen.queryByRole("button", { name: /salvar/i })).toBeNull();
    expect(api.put).not.toHaveBeenCalled();
  });

  it("shows each value with who changed it and when, and the support note", async () => {
    setup();
    expect((await screen.findByTestId("espec-valor-nome_empresa")).textContent).toBe("Lastro");
    expect(screen.getByTestId("espec-alterado-nome_empresa").textContent).toContain("Alterado por Ana Dona em ");
    expect(screen.getByTestId("espec-valor-horario").textContent).toBe("Não preenchido");
    expect(screen.getByTestId("espec-nota-suporte").textContent).toBe(NOTA_EDICAO_NOCTUS);
    expect(NOTA_EDICAO_NOCTUS).toBe("As especificações da Julia são configuradas pela equipe NoctusAI. Para alterar, fale com o suporte.");
  });

  it("flags a required value that is missing", async () => {
    setup();
    expect((await screen.findByTestId("espec-problema-horario")).textContent).toContain("Obrigatório");
  });

  it("skeleton first; empty declarations; the {data} envelope", async () => {
    setup();
    expect(screen.getByTestId("espec-skeleton")).toBeTruthy();
    await screen.findByTestId("espec-lista");
    cleanup();
    setup({ get: { ...ESPEC, declaradas: [], valores: [] } });
    expect(await screen.findByTestId("espec-vazio")).toBeTruthy();
    cleanup();
    setup({ get: { data: ESPEC } });
    expect(await screen.findByTestId("espec-lista")).toBeTruthy();
  });
});

describe("named refusals of the read", () => {
  it("409 agente_nao_conectado points to the connection card", async () => {
    setup({ get: erro(409, { error: { code: "agente_nao_conectado", message: "m" } }) });
    expect((await screen.findByTestId("espec-erro")).textContent).toContain("Conexão com a plataforma");
    expect(screen.getByTestId("espec-ver-conexao").getAttribute("href")).toBe("#conexao-plataforma");
  });

  it("502 agents_indisponivel is named and can be retried", { timeout: 10000 }, async () => {
    setup({ get: erro(502, { error: { code: "agents_indisponivel", message: "m" } }) });
    expect((await screen.findByTestId("espec-erro", {}, { timeout: 6000 })).textContent).toContain("indisponível");
  });
});

/**
 * Julia › Especificações do negócio (owner 2026-11-18): values shown with "Alterado por … em …"; an org ADMIN edits the keys agents
 * marks `editavel_pela_org` (except those with a dedicated card); a non-admin, and every non-editable key, stays read-only with a
 * note; typed refusals of the read and of the save are named.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import { EspecificacoesCard, NOTA_EDICAO_NOCTUS, NOTA_SOMENTE_ADMIN } from "./EspecificacoesCard";
import type { Especificacoes, TipoEspecificacao } from "@/hooks/useJuliaEspecificacoes";

const decl = (chave: string, tipo: TipoEspecificacao, over: Record<string, unknown> = {}) => ({
  id: `id-${chave}`, chave, rotulo: `Rótulo ${chave}`, descricao: null, tipo, obrigatoria: false, exemplo: null, ...over,
});

const ESPEC: Especificacoes = {
  agent_key: "julia", version_id: "v1", versao: 3,
  declaradas: [
    decl("titulo_profissional", "texto_curto", { obrigatoria: true, editavel_pela_org: true }), decl("horario", "horario"),
    decl("dominios", "dominios"), decl("conhecimento_venda", "texto_longo", { editavel_pela_org: true }),
  ],
  valores: [{ chave: "titulo_profissional", valor: "Lastro", updated_at: "2026-11-04T10:00:00Z", updated_by_nome: "Ana Dona" }],
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

describe("editing by an org admin", () => {
  it("an admin gets an input only for an editable key without its own card; non-editable keys stay text", async () => {
    setup({ admin: true });
    await screen.findByTestId("espec-lista");
    expect(screen.getByTestId("espec-input-titulo_profissional")).toBeTruthy();
    expect(screen.queryByTestId("espec-input-horario")).toBeNull();
    expect(screen.queryByTestId("espec-input-conhecimento_venda")).toBeNull();
    expect(document.querySelectorAll("textarea")).toHaveLength(1);
  });

  it("a non-admin has no inputs and no save, and sees the admin-only note", async () => {
    setup({ admin: false });
    await screen.findByTestId("espec-lista");
    expect(document.querySelectorAll("input, textarea, select")).toHaveLength(0);
    expect(screen.queryByTestId("espec-salvar")).toBeNull();
    expect(screen.getByTestId("espec-nota-suporte").textContent).toBe(NOTA_SOMENTE_ADMIN);
    expect(api.put).not.toHaveBeenCalled();
  });

  it("saves only the changed key and shows the server's answer without a stale draft", async () => {
    setup({ admin: true });
    api.put.mockResolvedValue({
      ...ESPEC, valores: [{ chave: "titulo_profissional", valor: "Corretor de imóveis", updated_at: "2026-11-18T10:00:00Z", updated_by_nome: "Ana Dona" }],
    });
    fireEvent.change(await screen.findByTestId("espec-input-titulo_profissional"), { target: { value: "Corretor de imóveis" } });
    expect(screen.getByTestId("espec-nao-salvo-titulo_profissional")).toBeTruthy();
    fireEvent.click(screen.getByTestId("espec-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put.mock.calls[0]).toEqual(["/api/julia/especificacoes", { valores: { titulo_profissional: "Corretor de imóveis" } }]);
    await waitFor(() => expect(screen.queryByTestId("espec-nao-salvo-titulo_profissional")).toBeNull());
  });

  it("a refusal on save is shown in pt-BR, never swallowed", async () => {
    setup({ admin: true });
    api.put.mockRejectedValue(erro(422, { code: "spec_nao_editavel_pela_org", detail: "x" }));
    fireEvent.change(await screen.findByTestId("espec-input-titulo_profissional"), { target: { value: "Novo" } });
    fireEvent.click(screen.getByTestId("espec-salvar"));
    expect((await screen.findByTestId("espec-erro-salvar")).textContent).toContain("equipe NoctusAI");
  });
});

describe("read side", () => {
  it("shows each value with who changed it and when, and the staff note for an admin", async () => {
    setup({ admin: false });
    expect((await screen.findByTestId("espec-valor-titulo_profissional")).textContent).toBe("Lastro");
    expect(screen.getByTestId("espec-alterado-titulo_profissional").textContent).toContain("Alterado por Ana Dona em ");
    expect(screen.getByTestId("espec-valor-horario").textContent).toBe("Não preenchido");
    cleanup();
    setup({ admin: true });
    expect((await screen.findByTestId("espec-nota-suporte")).textContent).toBe(NOTA_EDICAO_NOCTUS);
  });
});

  it("flags a required value that is missing", async () => {
    setup({ get: { ...ESPEC, valores: [], faltando: ["horario"] } });
    expect((await screen.findByTestId("espec-problema-titulo_profissional")).textContent).toContain("Obrigatório");
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

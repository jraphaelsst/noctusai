/**
 * Julia › Agente cards "Contatos por setor" (owner 2026-11-17) and "Conhecimento" editor (Lais study S8).
 * `@/lib/api` is the seam (real hooks + real components). Fictitious data only.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import { ConhecimentoEditorCard } from "./ConhecimentoEditorCard";
import { ContatosSetoriaisCard } from "./ContatosSetoriaisCard";

const DONO = { setor: "proprietarios", finalidade: "Proprietário da imobiliária", nome: "Dono Exemplo", telefone: "+5511900000001", origem: "perfil" };
const BASE = { dono: DONO, contatos: [], legado: [], setores: ["juridico", "parcerias"], maximo: 10, declarada: true };
const JURIDICO = { setor: "juridico", finalidade: "Contratos e dúvidas jurídicas", nome: "Dra. Exemplo", telefone: "+5511988887777" };

function renderCard(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}
function serverError(code: string, status = 403) {
  return Object.assign(new Error(`[${status}] x`), { status, body: { error: { code, message: "msg" } } });
}

beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));
afterEach(cleanup);

describe("ContatosSetoriaisCard", () => {
  it("skeleton first, then the read-only owner entry and the empty state", async () => {
    api.get.mockResolvedValue({ data: BASE });
    renderCard(<ContatosSetoriaisCard isAdmin />);
    expect(screen.getByTestId("contatos-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("contatos-dono")).toBeTruthy();
    expect(screen.getByTestId("contatos-dono").textContent).toContain("+5511900000001");
    expect(screen.getByTestId("contatos-dono").textContent).toContain("Vem do perfil");
    expect(screen.getByTestId("contatos-vazio")).toBeTruthy();
  });

  it("an owner without a phone says so instead of inventing an entry", async () => {
    api.get.mockResolvedValue({ data: { ...BASE, dono: null } });
    renderCard(<ContatosSetoriaisCard isAdmin />);
    expect(await screen.findByTestId("contatos-dono-ausente")).toBeTruthy();
  });

  it("error state offers a retry", async () => {
    api.get.mockRejectedValue(serverError("agente_nao_conectado", 409));
    renderCard(<ContatosSetoriaisCard isAdmin />);
    expect(await screen.findByTestId("contatos-erro")).toBeTruthy();
    expect(screen.getByText("Tentar de novo")).toBeTruthy();
  });

  it("adds a contact: draft is marked unsaved, validation blocks a bad phone, a good save sends the list", async () => {
    api.get.mockResolvedValue({ data: BASE });
    api.put.mockResolvedValue({ data: { ...BASE, contatos: [JURIDICO] } });
    renderCard(<ContatosSetoriaisCard isAdmin />);
    await screen.findByTestId("contatos-dono");
    fireEvent.click(screen.getByText("Adicionar contato"));
    expect(screen.getByTestId("contatos-nao-salvo")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Nome do contato 1"), { target: { value: "Dra. Exemplo" } });
    fireEvent.change(screen.getByLabelText("Finalidade do contato 1"), { target: { value: "Contratos e dúvidas jurídicas" } });
    fireEvent.change(screen.getByLabelText("Telefone do contato 1"), { target: { value: "abc" } });
    fireEvent.click(screen.getByText("Salvar contatos"));
    expect(await screen.findByTestId("contato-problema-0")).toBeTruthy();
    expect(api.put).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Telefone do contato 1"), { target: { value: "(11) 98888-7777" } });
    fireEvent.click(screen.getByText("Salvar contatos"));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put.mock.calls[0][0]).toBe("/api/julia/contatos-setoriais");
    expect(api.put.mock.calls[0][1].contatos).toEqual([
      { setor: "juridico", finalidade: "Contratos e dúvidas jurídicas", nome: "Dra. Exemplo", telefone: "(11) 98888-7777" },
    ]);
    await waitFor(() => expect(screen.queryByTestId("contatos-nao-salvo")).toBeNull());
  });

  it("a refusal is shown, never swallowed", async () => {
    api.get.mockResolvedValue({ data: { ...BASE, contatos: [JURIDICO] } });
    api.put.mockRejectedValue(serverError("agents_indisponivel", 502));
    renderCard(<ContatosSetoriaisCard isAdmin />);
    await screen.findByTestId("contatos-lista");
    fireEvent.change(screen.getByLabelText("Nome do contato 1"), { target: { value: "Outra Pessoa" } });
    fireEvent.click(screen.getByText("Salvar contatos"));
    expect((await screen.findByTestId("contatos-erro-salvar")).textContent).toContain("Não foi possível falar com a Julia agora");
  });

  it("a non-admin sees the list without inputs to change it", async () => {
    api.get.mockResolvedValue({ data: { ...BASE, contatos: [JURIDICO] } });
    renderCard(<ContatosSetoriaisCard isAdmin={false} />);
    await screen.findByTestId("contatos-lista");
    expect((screen.getByLabelText("Nome do contato 1") as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByText("Salvar contatos")).toBeNull();
  });

  it("shows legacy items instead of dropping them silently", async () => {
    api.get.mockResolvedValue({ data: { ...BASE, legado: ["+5511911112222"] } });
    renderCard(<ContatosSetoriaisCard isAdmin />);
    expect((await screen.findByTestId("contatos-legado")).textContent).toContain("+5511911112222");
  });
});

const EDITOR = {
  max_chars: 4000,
  itens: [
    { chave: "conhecimento_venda", rotulo: "Vendas", valor: "Aceitamos financiamento.", declarada: true, updated_at: null, updated_by_nome: null, sugestao: null },
    { chave: "conhecimento_locacao", rotulo: "Locação", valor: "", declarada: true, updated_at: null, updated_by_nome: null, sugestao: "## Locação\n- caução" },
    { chave: "conhecimento_politicas", rotulo: "Políticas e informações gerais", valor: "", declarada: false, updated_at: null, updated_by_nome: null, sugestao: null },
  ],
};

describe("ConhecimentoEditorCard", () => {
  it("renders the three texts, the legacy suggestion only on an empty one, and flags an undeclared key", async () => {
    api.get.mockResolvedValue({ data: EDITOR });
    renderCard(<ConhecimentoEditorCard isAdmin />);
    expect(screen.getByTestId("conhecimento-skeleton")).toBeTruthy();
    expect(((await screen.findByLabelText("Vendas")) as HTMLTextAreaElement).value).toBe("Aceitamos financiamento.");
    expect(screen.queryByTestId("conhecimento-sugestao-conhecimento_venda")).toBeNull();
    expect(screen.getByTestId("conhecimento-sugestao-conhecimento_locacao")).toBeTruthy();
    expect(screen.getByTestId("conhecimento-nao-declarada-conhecimento_politicas")).toBeTruthy();
  });

  it("fills a draft from the old form without saving, then saves only the changed key", async () => {
    api.get.mockResolvedValue({ data: EDITOR });
    api.put.mockResolvedValue({
      data: { ...EDITOR, itens: EDITOR.itens.map((i) => (i.chave === "conhecimento_locacao" ? { ...i, valor: "## Locação\n- caução", sugestao: null } : i)) },
    });
    renderCard(<ConhecimentoEditorCard isAdmin />);
    fireEvent.click(await screen.findByTestId("conhecimento-sugestao-conhecimento_locacao"));
    expect(api.put).not.toHaveBeenCalled();
    expect(screen.getByTestId("conhecimento-nao-salvo-conhecimento_locacao")).toBeTruthy();
    fireEvent.click(screen.getByText("Salvar conhecimento"));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put.mock.calls[0][1]).toEqual({ valores: { conhecimento_locacao: "## Locação\n- caução" } });
    await waitFor(() => expect(screen.queryByTestId("conhecimento-nao-salvo-conhecimento_locacao")).toBeNull());
  });

  it("blocks a text over the limit and shows the counter", async () => {
    api.get.mockResolvedValue({ data: { ...EDITOR, max_chars: 10 } });
    renderCard(<ConhecimentoEditorCard isAdmin />);
    fireEvent.change(await screen.findByLabelText("Vendas"), { target: { value: "x".repeat(11) } });
    expect(screen.getByTestId("conhecimento-contador-conhecimento_venda").textContent).toBe("11/10");
    expect((screen.getByText("Salvar conhecimento") as HTMLButtonElement).disabled).toBe(true);
  });

  it("a refused save shows the pt-BR sentence and keeps the draft", async () => {
    api.get.mockResolvedValue({ data: EDITOR });
    api.put.mockRejectedValue(serverError("agents_indisponivel", 502));
    renderCard(<ConhecimentoEditorCard isAdmin />);
    fireEvent.change(await screen.findByLabelText("Vendas"), { target: { value: "novo" } });
    fireEvent.click(screen.getByText("Salvar conhecimento"));
    expect((await screen.findByTestId("conhecimento-erro-salvar")).textContent).toContain("Não foi possível falar com a Julia agora");
  });

  it("error state offers a retry", async () => {
    api.get.mockRejectedValue(serverError("agente_nao_conectado", 409));
    renderCard(<ConhecimentoEditorCard isAdmin />);
    expect(await screen.findByTestId("conhecimento-erro")).toBeTruthy();
  });
});

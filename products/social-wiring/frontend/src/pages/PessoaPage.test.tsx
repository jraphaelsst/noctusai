/** One component, two routes: section order differs by role (decision D3). */
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ usePessoaResumo: vi.fn() }));
vi.mock("@/hooks/usePessoa", () => ({ usePessoaResumo: m.usePessoaResumo }));
// The two sections are tested on their own; here only their ORDER matters.
vi.mock("@/components/interesses/ImovelInteressesList", () => ({
  ImovelInteressesList: (p: { clienteId: string; atendimentoId?: string }) => (
    <div data-testid="sec-interesses" data-atendimento={p.atendimentoId ?? ""} />
  ),
}));
vi.mock("@/components/interesses/ProprietariosSection", () => ({
  ProprietariosSection: (p: { titulo: string }) => (
    <div data-testid="sec-propriedades">{p.titulo}</div>
  ),
}));

import { cleanup, render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import PessoaPage from "./PessoaPage";
import type { PessoaResumo } from "@/types/pessoa";

afterEach(() => {
  cleanup();
  m.usePessoaResumo.mockReset();
});

const resumo: PessoaResumo = {
  cliente: { id: "c1", nome: "Ana", nome_oficial: "Ana Souza", cpf: null, celular: "48999990000", email: "ana@x.com" },
  papeis: ["comprador", "vendedor"],
  contatos: { celular: "48999990000", email: "ana@x.com", chave_canonica: null },
  atendimentos: [
    {
      id: "at1",
      titulo: "Compra apto",
      etapa: { id: "e1", nome: "Visita" },
      status: "ativo",
      arquivado: false,
      titular: true,
      lado: "comprador",
      papel: null,
      parte_id: null,
      imovel_pendente: false,
      imoveis: ["ONE9001"],
      created_at: "2026-09-01T10:00:00Z",
    },
  ],
  contagens: { interesses: 2, propriedades: 1, roteiros: 0, atendimentos: 1 },
};

function renderEm(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/clientes/:id" element={<PessoaPage />} />
        <Route path="/vendedores/:id" element={<PessoaPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function ordem(c: HTMLElement) {
  return Array.from(c.querySelectorAll("[data-testid^='sec-']")).map((e) =>
    e.getAttribute("data-testid"),
  );
}

describe("PessoaPage", () => {
  it("comprador route: header → Interesses → 'Imóveis que possui' at the bottom", () => {
    m.usePessoaResumo.mockReturnValue({ data: resumo, isPending: false, isFetching: false, isError: false });
    const { container, getByTestId } = renderEm("/clientes/c1");
    expect(m.usePessoaResumo).toHaveBeenCalledWith("c1");
    expect(getByTestId("pessoa-page-comprador")).toBeTruthy();
    expect(ordem(container)).toEqual(["sec-interesses", "sec-propriedades"]);
    expect(getByTestId("sec-propriedades").textContent).toBe("Imóveis que possui");
    // Header precedes both sections.
    const html = container.innerHTML;
    expect(html.indexOf("pessoa-cabecalho")).toBeLessThan(html.indexOf("sec-interesses"));
  });

  it("vendedor route: header → 'Imóveis à venda' → Interesses at the bottom", () => {
    m.usePessoaResumo.mockReturnValue({ data: resumo, isPending: false, isFetching: false, isError: false });
    const { container, getByTestId } = renderEm("/vendedores/c1");
    expect(getByTestId("pessoa-page-vendedor")).toBeTruthy();
    expect(ordem(container)).toEqual(["sec-propriedades", "sec-interesses"]);
    expect(getByTestId("sec-propriedades").textContent).toBe("Imóveis à venda");
  });

  it("header shows nome oficial, papéis, WhatsApp link and the atendimentos", () => {
    m.usePessoaResumo.mockReturnValue({ data: resumo, isPending: false, isFetching: false, isError: false });
    const { getByTestId } = renderEm("/clientes/c1");
    expect(getByTestId("pessoa-cabecalho").textContent).toContain("Ana Souza");
    expect(getByTestId("pessoa-papeis").textContent).toContain("Comprador");
    expect(getByTestId("pessoa-papeis").textContent).toContain("Vendedor");
    expect(getByTestId("pessoa-whatsapp").getAttribute("href")).toBe("https://wa.me/5548999990000");
    expect(getByTestId("pessoa-atendimento-at1").textContent).toContain("Compra apto");
  });

  it("passes the only open atendimento down (roteiro POST never 409s)", () => {
    m.usePessoaResumo.mockReturnValue({ data: resumo, isPending: false, isFetching: false, isError: false });
    const { getByTestId } = renderEm("/clientes/c1");
    expect(getByTestId("sec-interesses").getAttribute("data-atendimento")).toBe("at1");
  });

  it("loading skeleton only on first load; error state; refetch keeps content", () => {
    m.usePessoaResumo.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    const a = renderEm("/clientes/c1");
    expect(a.queryByTestId("pessoa-loading")).toBeTruthy();
    a.unmount();

    m.usePessoaResumo.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    const b = renderEm("/clientes/c1");
    expect(b.queryByTestId("pessoa-erro")).toBeTruthy();
    b.unmount();

    m.usePessoaResumo.mockReturnValue({ data: resumo, isPending: false, isFetching: true, isError: false });
    const c = renderEm("/clientes/c1");
    expect(c.queryByTestId("pessoa-cabecalho")).toBeTruthy();
    expect(c.queryByTestId("pessoa-refreshing")).toBeTruthy();
    expect(c.queryByTestId("pessoa-loading")).toBeNull();
  });
});

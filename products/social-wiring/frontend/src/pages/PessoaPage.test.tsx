/** One component, two routes: section order differs by role (decision D3). */
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  usePessoaResumo: vi.fn(),
  role: { current: "member" as string },
  mutate: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: m.toastSuccess, error: m.toastError, warning: vi.fn() } }));
vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: () => ({ user: { user_metadata: { org_role: m.role.current } } }),
}));
// useIsOrgAdmin (seed) runs for real over the mocked auth store above.
vi.mock("@/hooks/useClientes", () => ({
  useClienteMutations: () => ({ remove: { mutate: m.mutate, isPending: false } }),
}));
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

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import PessoaPage from "./PessoaPage";
import type { PessoaResumo } from "@/types/pessoa";

afterEach(() => {
  cleanup();
  m.usePessoaResumo.mockReset();
  m.mutate.mockReset();
  m.toastError.mockReset();
  m.role.current = "member";
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
        <Route path="/clientes" element={<div data-testid="lista-clientes" />} />
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

  describe("Excluir cliente", () => {
    const pronto = () =>
      m.usePessoaResumo.mockReturnValue({ data: resumo, isPending: false, isFetching: false, isError: false });

    it("is hidden for a non-admin", () => {
      pronto();
      renderEm("/clientes/c1");
      expect(screen.queryByTestId("pessoa-excluir")).toBeNull();
    });

    it("admin: confirm dialog names the person, confirm deletes and navigates to /clientes", () => {
      m.role.current = "admin";
      pronto();
      m.mutate.mockImplementation((_id, opts) => opts.onSuccess({ storage_falhas: [] }));
      renderEm("/clientes/c1");
      fireEvent.click(screen.getByTestId("pessoa-excluir"));
      expect(screen.getByText("Ana Souza", { selector: "strong" })).toBeTruthy();
      fireEvent.click(screen.getByTestId("excluir-cliente-confirm"));
      expect(m.mutate).toHaveBeenCalledWith("c1", expect.any(Object));
      expect(screen.getByTestId("lista-clientes")).toBeTruthy();
    });

    it("success toast says the person won't come back from their leads", () => {
      m.role.current = "admin";
      pronto();
      m.mutate.mockImplementation((_id, opts) =>
        opts.onSuccess({ storage_falhas: [], origens_bloqueadas: 2 }),
      );
      renderEm("/clientes/c1");
      fireEvent.click(screen.getByTestId("pessoa-excluir"));
      fireEvent.click(screen.getByTestId("excluir-cliente-confirm"));
      expect(m.toastSuccess).toHaveBeenCalledWith(expect.stringMatching(/não voltará.*2 lead\(s\)/));
    });

    it("surfaces the API's 409 message and stays on the page", () => {
      m.role.current = "owner";
      pronto();
      m.mutate.mockImplementation((_id, opts) =>
        opts.onError({ body: { error: { message: "Cliente é sobrevivente de unificação" } } }),
      );
      renderEm("/clientes/c1");
      fireEvent.click(screen.getByTestId("pessoa-excluir"));
      fireEvent.click(screen.getByTestId("excluir-cliente-confirm"));
      expect(m.toastError).toHaveBeenCalledWith("Cliente é sobrevivente de unificação");
      expect(screen.queryByTestId("lista-clientes")).toBeNull();
    });
  });
});

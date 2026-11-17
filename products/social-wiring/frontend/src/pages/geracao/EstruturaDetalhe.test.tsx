/**
 * Estrutura detail: a MEMBER gets the read-only view (no provenance, no admin controls, no editor); an ADMIN
 * gets the editor; a 404 is its own state. The admin/member split is asserted on the rendered DOM, never on props.
 */
import { ConfirmProvider } from "@noctusai/lib/components";
import * as rtl from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const m = vi.hoisted(() => ({ admin: vi.fn(), detalhe: vi.fn(), tipos: vi.fn() }));
vi.mock("@/hooks/geracao/useEstruturas", () => {
  const mut = () => ({ mutateAsync: vi.fn(), isPending: false });
  return {
    useEstruturasAdmin: () => m.admin(),
    useEstruturaDetalhe: () => m.detalhe(),
    useTiposBloco: () => m.tipos(),
    useAtualizarEstrutura: mut,
    useSubstituirBlocos: mut,
    useConfirmarEstrutura: mut,
    usePublicarEstrutura: mut,
    useArquivarEstrutura: mut,
    useExcluirEstrutura: mut,
  };
});

import { detalheAdmin, membro, TIPOS } from "@/test/estruturasFixtures";
import EstruturaDetalhePage from "./EstruturaDetalhe";

const q = (data: unknown, over: Record<string, unknown> = {}) => ({
  data,
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  error: null,
  failureCount: 0,
  isFetching: false,
  refetch: vi.fn().mockResolvedValue({ data }),
  ...over,
});

function renderPage() {
  rtl.render(
    <MemoryRouter initialEntries={["/media-creation/biblioteca/estruturas/e1"]}>
      <ConfirmProvider>
        <Routes>
          <Route path="/media-creation/biblioteca/estruturas/:id" element={<EstruturaDetalhePage />} />
          <Route path="/media-creation/biblioteca" element={<div>lista</div>} />
        </Routes>
      </ConfirmProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  m.admin.mockReturnValue({ data: false });
  m.tipos.mockReturnValue(q(TIPOS));
  m.detalhe.mockReturnValue(q(membro(detalheAdmin())));
});

describe("member", () => {
  it("sees formula, ordered blocks with tempo / instrução / nota / ×N, the profile link and 'Usar no chat'", () => {
    renderPage();
    expect(rtl.screen.getByRole("heading", { name: "Estrutura #101" })).toBeTruthy();
    expect(rtl.screen.getByText("Como [autoridade teórica] resolve [problema]")).toBeTruthy();
    expect(rtl.screen.getByRole("link", { name: "@criador.exemplo" }).getAttribute("href")).toBe("/media-creation/biblioteca/perfis/p1");
    expect(rtl.screen.getByRole("link", { name: /Usar no chat/ }).getAttribute("href")).toBe("/media-creation/chat?estrutura=e1");
    const b1 = rtl.screen.getByTestId("bloco-leitura-1");
    expect(b1.textContent).toContain("Gancho inicial");
    expect(b1.textContent).toContain("Headline");
    expect(b1.textContent).toContain("0–3s");
    const b2 = rtl.screen.getByTestId("bloco-leitura-2");
    expect(b2.textContent).toContain("×2");
    expect(b2.textContent).toContain("O vídeo original fecha com uma pergunta.");
    // an empty instrução falls back to the type's reference instruction
    expect(b2.textContent).toContain("Peça para salvar.");
  });

  it("sees NO provenance, editor, confirm/publish bars or admin metadata", () => {
    renderPage();
    for (const t of ["Preenchido por referência", "Sugerido pela IA", "Confirmar todos", "Publicar", "Salvar", "Arquivar", "Excluir", "Adicionar bloco"]) {
      expect(rtl.screen.queryByText(t)).toBeNull();
    }
    expect(rtl.screen.queryByTestId("estrutura-editor")).toBeNull();
    expect(rtl.screen.queryByTestId("estrutura-origem")).toBeNull();
    expect(rtl.screen.queryByTestId("proveniencia-badge")).toBeNull();
    expect(rtl.screen.queryByText("Rascunho")).toBeNull();
  });
});

describe("admin", () => {
  it("gets the editor, the provenance badges, the origin line and the catalog-backed block editor", () => {
    m.admin.mockReturnValue({ data: true });
    m.detalhe.mockReturnValue(q(detalheAdmin()));
    renderPage();
    expect(rtl.screen.getByTestId("estrutura-editor")).toBeTruthy();
    expect(rtl.screen.getAllByTestId("proveniencia-badge")).toHaveLength(3);
    expect(rtl.screen.getByTestId("estrutura-origem").textContent).toContain("Importada (referência CoreStudio)");
    expect(rtl.screen.getByLabelText("Tipo do bloco 1")).toBeTruthy();
    expect(rtl.screen.queryByTestId("estrutura-leitura")).toBeNull();
  });

  it("the editor waits for the catalog (skeleton) and offers a retry when it cannot load", () => {
    m.admin.mockReturnValue({ data: true });
    m.detalhe.mockReturnValue(q(detalheAdmin()));
    m.tipos.mockReturnValue(q(undefined, { showSkeleton: true }));
    renderPage();
    expect(rtl.screen.queryByTestId("estrutura-editor")).toBeNull();
    rtl.cleanup();
    m.tipos.mockReturnValue(q(undefined, { isError: true, error: new Error("x") }));
    renderPage();
    expect(rtl.screen.getByText("Não foi possível carregar os tipos de bloco.")).toBeTruthy();
  });

  it("a rascunho shows its status badge only to the admin", () => {
    m.admin.mockReturnValue({ data: true });
    m.detalhe.mockReturnValue(q(detalheAdmin({ status: "rascunho" })));
    renderPage();
    expect(rtl.screen.getAllByText("Rascunho").length).toBeGreaterThan(0);
    // and there is no "Usar no chat" for something orgs cannot use yet
    expect(rtl.screen.queryByRole("link", { name: /Usar no chat/ })).toBeNull();
  });
});

describe("states", () => {
  it("skeleton while loading", () => {
    m.detalhe.mockReturnValue(q(undefined, { showSkeleton: true }));
    renderPage();
    expect(rtl.screen.getByLabelText("Carregando estrutura")).toBeTruthy();
  });

  it("404 (also a rascunho/arquivada to a member) is 'não encontrada', not a blank page", () => {
    m.detalhe.mockReturnValue(q(undefined, { isError: true, error: Object.assign(new Error("x"), { status: 404 }) }));
    renderPage();
    expect(rtl.screen.getByText("Estrutura não encontrada")).toBeTruthy();
    expect(rtl.screen.getByRole("link", { name: /Voltar para a Biblioteca/ }).getAttribute("href")).toBe("/media-creation/biblioteca?aba=estruturas");
  });

  it("any other failure is a retryable block", () => {
    m.detalhe.mockReturnValue(q(undefined, { isError: true, error: new Error("boom") }));
    renderPage();
    expect(rtl.screen.getByRole("button", { name: /Tentar novamente/ })).toBeTruthy();
    expect(rtl.screen.queryByText("Estrutura não encontrada")).toBeNull();
  });
});

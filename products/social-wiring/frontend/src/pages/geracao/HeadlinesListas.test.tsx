/** Favoritas + Sugeridas: columns per list, ?hid= highlight, Criar roteiro prefill, actions. */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HeadlinesFavoritas from "./HeadlinesFavoritas";
import HeadlinesSugeridas from "./HeadlinesSugeridas";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const m = vi.hoisted(() => ({
  lista: vi.fn(),
  um: vi.fn(),
  favoritar: vi.fn(),
  excluir: vi.fn(),
  agora: vi.fn(),
  roteiroProps: vi.fn(),
  listaArgs: vi.fn(),
}));

vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }),
}));
vi.mock("@/hooks/geracao/useHeadlines", () => ({
  HEADLINES_PAGE_SIZE: 20,
  useHeadlinesLista: (...a: unknown[]) => {
    m.listaArgs(...a);
    return m.lista();
  },
  useHeadline: (id: string | null) => m.um(id),
  useGerarSugestoesAgora: () => ({ mutateAsync: m.agora, isPending: false }),
}));
vi.mock("@/hooks/geracao/useHeadlineMutations", () => ({
  useFavoritarHeadline: () => ({ mutateAsync: m.favoritar, isPending: false }),
  useExcluirHeadlines: () => ({ mutateAsync: m.excluir, isPending: false }),
  useEditarHeadline: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/components/geracao/roteiro/RoteiroAvancadoModal", () => ({
  RoteiroAvancadoModal: (p: any) => {
    m.roteiroProps(p);
    return p.open ? <div role="dialog">Roteiro Avançado: {p.headlineInicial?.texto}</div> : null;
  },
}));

const ok = <T,>(data: T) => ({ data, showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn() });
const hl = (over: Partial<any> = {}) => ({
  id: "h1",
  marca_id: "m1",
  lote_id: "l1",
  texto: "Headline um",
  texto_original: null,
  viral: null,
  favorita: true,
  modo: null,
  roteiro_id: null,
  created_at: "2026-10-09T10:00:00Z",
  ...over,
});

function renderPage(ui: React.ReactElement, url = "/x") {
  return rtl.render(<MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  m.lista.mockReturnValue(ok({ items: [hl()], total: 1 }));
  m.um.mockReturnValue(ok(undefined));
});

describe("Favoritas", () => {
  it("mostra a headline com o selo 'Roteiro criado' apontando para o roteiro", () => {
    m.lista.mockReturnValue(ok({ items: [hl({ roteiro_id: "r9" })], total: 1 }));
    renderPage(<HeadlinesFavoritas />);
    expect(rtl.screen.getByText("Headlines Favoritas")).toBeTruthy();
    expect(rtl.screen.getByText("Headline um")).toBeTruthy();
    expect(rtl.screen.getByText("Roteiro criado").closest("a")?.getAttribute("href")).toBe("/media-creation/roteiros?open=r9");
    expect(rtl.screen.queryByText("Modo")).toBeNull();
    expect(m.listaArgs.mock.calls[0][1]).toBe("favoritas");
  });

  it("Criar roteiro abre o Roteiro Avançado preenchido com a headline", async () => {
    renderPage(<HeadlinesFavoritas />);
    await userEvent.click(rtl.screen.getByRole("button", { name: /Criar roteiro/ }));
    expect(await rtl.screen.findByText("Roteiro Avançado: Headline um")).toBeTruthy();
    expect(m.roteiroProps.mock.calls.at(-1)![0]).toMatchObject({
      marcaId: "m1",
      headlineInicial: { id: "h1", texto: "Headline um" },
    });
  });

  it("?hid= destaca a linha; fora da página busca a headline por id", () => {
    renderPage(<HeadlinesFavoritas />, "/x?hid=h1");
    expect(rtl.screen.getByTestId("headline-h1").getAttribute("data-destacada")).toBe("true");
    rtl.cleanup();
    m.um.mockImplementation((id: string | null) => ok(id === "h77" ? hl({ id: "h77", texto: "Fora da página" }) : undefined));
    renderPage(<HeadlinesFavoritas />, "/x?hid=h77");
    expect(rtl.screen.getByText("Fora da página")).toBeTruthy();
    expect(rtl.screen.getByTestId("headline-h77").getAttribute("data-destacada")).toBe("true");
  });

  it("desfavoritar chama a mutação com favoritar=false", async () => {
    m.favoritar.mockResolvedValue({});
    renderPage(<HeadlinesFavoritas />);
    await userEvent.click(rtl.screen.getByRole("button", { name: "Desfavoritar headline" }));
    expect(m.favoritar).toHaveBeenCalledWith({ id: "h1", favoritar: false });
  });

  it("exclui selecionadas depois de confirmar", async () => {
    m.excluir.mockResolvedValue({ excluidos: 1 });
    renderPage(<HeadlinesFavoritas />);
    await userEvent.click(rtl.screen.getByLabelText(/Selecionar headline de/));
    await userEvent.click(rtl.screen.getByRole("button", { name: /Excluir Selecionados \(1\)/ }));
    await userEvent.click(await rtl.screen.findByRole("button", { name: "Excluir" }));
    await rtl.waitFor(() => expect(m.excluir).toHaveBeenCalledWith(["h1"]));
  });

  it("vazio e erro têm estados próprios", () => {
    m.lista.mockReturnValue(ok({ items: [], total: 0 }));
    renderPage(<HeadlinesFavoritas />);
    expect(rtl.screen.getByText(/Você ainda não tem headlines favoritas/)).toBeTruthy();
    rtl.cleanup();
    m.lista.mockReturnValue({ ...ok(undefined), isError: true });
    renderPage(<HeadlinesFavoritas />);
    expect(rtl.screen.getByRole("alert").textContent).toContain("Não foi possível carregar as headlines.");
    expect(rtl.screen.getByRole("button", { name: "Tentar novamente" })).toBeTruthy();
  });
});

describe("Sugeridas", () => {
  const sugerida = hl({
    modo: "automatico",
    favorita: false,
    viral: { id: "v1", codigo: 5, views: 120000, likes: null, score_viral: 3, permalink: "https://instagram.com/p/x" },
  });

  it("mostra Modo, Métrica e Abrir link", () => {
    m.lista.mockReturnValue(ok({ items: [sugerida], total: 1 }));
    renderPage(<HeadlinesSugeridas />);
    expect(rtl.screen.getByText("Headline sugeridas")).toBeTruthy();
    expect(rtl.screen.getByText("Automático", { selector: "td" })).toBeTruthy();
    expect(rtl.screen.getByText(/120K views/)).toBeTruthy();
    expect(rtl.screen.getByRole("link", { name: "Abrir link do viral" }).getAttribute("href")).toBe("https://instagram.com/p/x");
    expect(m.listaArgs.mock.calls[0][1]).toBe("sugeridas");
  });

  it("filtro de modo vai para a consulta", async () => {
    renderPage(<HeadlinesSugeridas />);
    await userEvent.selectOptions(rtl.screen.getByLabelText("Modo"), "manual");
    await rtl.waitFor(() => expect(m.listaArgs.mock.calls.at(-1)![2]).toMatchObject({ modo: "manual" }));
  });

  it("Gerar sugestões agora dispara a mutação da marca", async () => {
    m.agora.mockResolvedValue({});
    renderPage(<HeadlinesSugeridas />);
    await userEvent.click(rtl.screen.getByRole("button", { name: /Gerar sugestões agora/ }));
    expect(m.agora).toHaveBeenCalledWith("m1");
  });

  it("favoritar uma sugerida chama favoritar=true", async () => {
    m.lista.mockReturnValue(ok({ items: [sugerida], total: 1 }));
    m.favoritar.mockResolvedValue({});
    renderPage(<HeadlinesSugeridas />);
    await userEvent.click(rtl.screen.getByRole("button", { name: "Favoritar headline" }));
    expect(m.favoritar).toHaveBeenCalledWith({ id: "h1", favoritar: true });
  });
});

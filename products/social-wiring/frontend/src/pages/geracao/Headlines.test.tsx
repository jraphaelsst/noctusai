/** Gerar headlines: landing cards, form per `who`, real progress, honest warnings, history actions. */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Headlines, { resolverWho } from "./Headlines";
import HeadlinesGerar from "./HeadlinesGerar";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const m = vi.hoisted(() => ({
  lotes: vi.fn(),
  lote: vi.fn(),
  criar: vi.fn(),
  contagem: vi.fn(),
  itens: vi.fn(),
  excluir: vi.fn(),
  reprocessar: vi.fn(),
  assuntos: vi.fn(),
}));

vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }),
}));
vi.mock("@/hooks/geracao/useHeadlines", () => ({
  HEADLINES_PAGE_SIZE: 20,
  useLotes: () => m.lotes(),
  useLote: () => m.lote(),
  useCriarLote: () => ({ mutateAsync: m.criar, isPending: false }),
  useReprocessarLote: () => ({ mutateAsync: m.reprocessar, isPending: false }),
  useExcluirLotes: () => ({ mutateAsync: m.excluir, isPending: false }),
  useContagemEstruturas: () => m.contagem(),
  useItensAprovados: () => m.itens(),
}));
vi.mock("@/hooks/geracao/useHeadlineMutations", () => ({
  useFavoritarHeadline: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useEditarHeadline: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/hooks/usePesquisa", () => ({
  usePesquisaVariaveis: () => ({
    data: [
      { slug: "crencas", label: "Crenças", grupo: "especialista", description: "d", sort_order: 1 },
      { slug: "dores", label: "Dores do público", grupo: "publico", description: "d", sort_order: 1 },
    ],
    showSkeleton: false,
    isError: false,
  }),
}));
vi.mock("@/hooks/useAssuntosVirais", () => ({ useAssuntosVirais: () => m.assuntos() }));
vi.mock("@/hooks/geracao/useTaxonomias", () => ({
  useTaxonomias: () => ({
    data: {
      formatos: [{ id: 1, nome: "Lista", definicao: "x" }],
      gatilhos: [{ slug: "misterio", nome: "Mistério", formula: "f" }],
      tons: [
        { id: 10, nome: "Chocante e Disruptiva" },
        { id: 11, nome: "Futuro e Possibilidades" },
      ],
    },
    showSkeleton: false,
    isError: false,
  }),
}));
vi.mock("@/hooks/geracao/useBiblioteca", () => ({
  usePerfisMonitorados: () => ({
    data: [
      { id: "p1", handle: "com_estrutura", status: "ativo", virais: 3 },
      { id: "p2", handle: "sem_estrutura", status: "ativo", virais: 1 },
    ],
  }),
  useViralDetalhe: () => ({ data: undefined, showSkeleton: false }),
}));
vi.mock("@/components/geracao/biblioteca/ViralModal", () => ({ ViralModal: () => null }));
vi.mock("@/components/geracao/roteiro/RoteiroAvancadoModal", () => ({ RoteiroAvancadoModal: () => null }));

const ok = <T,>(data: T) => ({ data, showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn() });
const lote = (over: Partial<any> = {}) => ({
  id: "l1",
  marca_id: "m1",
  origem: "form_me",
  status: "completo",
  etapa: null,
  estruturas_total: 5,
  estruturas_processadas: 5,
  estruturas_com_erro: 0,
  aviso_poucas_estruturas: false,
  fallback_metodo: false,
  erro: null,
  resumo: "Crenças",
  created_at: "2026-10-09T10:00:00Z",
  finished_at: null,
  ...over,
});

function renderPage(url = "/media-creation/headlines?who=me") {
  return rtl.render(
    <MemoryRouter initialEntries={[url]}>
      <Headlines />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  m.lotes.mockReturnValue(ok({ items: [lote()], total: 1 }));
  m.lote.mockReturnValue(ok({ ...lote(), parametros: {}, headlines: [] }));
  m.contagem.mockReturnValue({ data: undefined, isRefreshing: false });
  m.itens.mockReturnValue(ok([{ id: "i1", content: "Acredito em X" }]));
  m.assuntos.mockReturnValue({ ...ok(undefined), items: [{ id: "a1", topic: "Tema quente" }] });
  m.criar.mockResolvedValue(lote({ id: "novo", status: "criando" }));
});

describe("landing", () => {
  it("mostra os 3 cards que levam ao form com ?who=", () => {
    rtl.render(
      <MemoryRouter>
        <HeadlinesGerar />
      </MemoryRouter>,
    );
    expect(rtl.screen.getByText("Selecione o assunto que deseja gerar suas headlines")).toBeTruthy();
    const links = rtl.screen.getAllByRole("link", { name: "Gerar Headlines" }).map((a) => a.getAttribute("href"));
    expect(links).toEqual([
      "/media-creation/headlines?who=me",
      "/media-creation/headlines?who=public",
      "/media-creation/headlines?who=viral",
    ]);
  });
});

describe("resolverWho", () => {
  it("who desconhecido ou ausente vira viral", () => {
    expect(resolverWho("me")).toBe("me");
    expect(resolverWho("public")).toBe("public");
    expect(resolverWho("xyz")).toBe("viral");
    expect(resolverWho(null)).toBe("viral");
  });
});

describe("form por who", () => {
  it("me lista só as variáveis do especialista e envia o corpo do contrato", async () => {
    renderPage("/media-creation/headlines?who=me");
    expect(rtl.screen.getByText("Gerar headlines sobre Mim")).toBeTruthy();
    expect(rtl.screen.queryByLabelText("Dores do público")).toBeNull();
    await userEvent.click(rtl.screen.getByLabelText("Crenças"));
    expect(rtl.screen.getByText(/Valor das variável/)).toBeTruthy();
    await userEvent.click(rtl.screen.getByLabelText("Acredito em X"));
    await userEvent.click(rtl.screen.getByLabelText("Criar as headlines usando apenas os itens da minha pesquisa."));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Gerar Headlines" }));
    await rtl.waitFor(() => expect(m.criar).toHaveBeenCalledTimes(1));
    expect(m.criar).toHaveBeenCalledWith({
      marca_id: "m1",
      origem: "form_me",
      variaveis: ["crencas"],
      valores: { crencas: ["i1"] },
      somente_pesquisa: true,
      criatividade: "equilibrado",
    });
  });

  it("public usa form_public e Todos manda ['*']", async () => {
    renderPage("/media-creation/headlines?who=public");
    expect(rtl.screen.getByText("Gerar headlines sobre Meu publico")).toBeTruthy();
    await userEvent.click(rtl.screen.getByLabelText("Todos"));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Gerar Headlines" }));
    await rtl.waitFor(() => expect(m.criar).toHaveBeenCalled());
    expect(m.criar.mock.calls[0][0]).toMatchObject({ origem: "form_public", variaveis: ["*"] });
  });

  it("gerar fica desabilitado sem variável selecionada", () => {
    renderPage("/media-creation/headlines?who=me");
    expect((rtl.screen.getByRole("button", { name: "Gerar Headlines" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("desabilita perfis sem estruturas e avisa quando há variáveis selecionadas", async () => {
    m.contagem.mockReturnValue({
      data: { compativeis: 2, por_perfil: [{ perfil_id: "p1", n: 2 }] },
      isRefreshing: false,
    });
    renderPage("/media-creation/headlines?who=me");
    await userEvent.click(rtl.screen.getByLabelText("Crenças"));
    await userEvent.click(rtl.screen.getByLabelText("Modelagem de um Perfil"));
    expect(rtl.screen.getByText(/Exibindo somente perfis que possuem estruturas/)).toBeTruthy();
    expect((rtl.screen.getByLabelText("@sem_estrutura") as HTMLButtonElement).getAttribute("data-disabled")).not.toBeNull();
    expect(rtl.screen.getByText("(Sem estruturas disponíveis)")).toBeTruthy();
    expect((rtl.screen.getByLabelText("@com_estrutura") as HTMLButtonElement).getAttribute("data-disabled")).toBeNull();
  });

  it("viral (e who desconhecido): assuntos aprovados, passo do tom e corpo form_viral", async () => {
    renderPage("/media-creation/headlines?who=zzz");
    expect(rtl.screen.getByText("Gerar headlines sobre Assuntos virais")).toBeTruthy();
    await userEvent.click(rtl.screen.getByLabelText("Tema quente"));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Selecionar Assunto" }));
    expect(rtl.screen.getByText("Tom de Comunicação:")).toBeTruthy();
    await userEvent.click(rtl.screen.getByLabelText("Chocante e Disruptiva"));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Gerar Headlines" }));
    await rtl.waitFor(() => expect(m.criar).toHaveBeenCalled());
    expect(m.criar.mock.calls[0][0]).toMatchObject({ origem: "form_viral", assunto_ids: ["a1"], tom: 10 });
  });

  it("viral sem assuntos aprovados explica e aceita assunto livre", async () => {
    m.assuntos.mockReturnValue({ ...ok({ pages: [] }), items: [] });
    renderPage("/media-creation/headlines?who=viral");
    expect(rtl.screen.getByText(/Nenhum assunto viral disponível no momento/)).toBeTruthy();
    expect((rtl.screen.getByRole("button", { name: "Selecionar Assunto" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(rtl.screen.getByLabelText("Sobre o que você deseja falar:"), "meu tema");
    expect((rtl.screen.getByRole("button", { name: "Selecionar Assunto" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("progresso real", () => {
  it("mostra etapa e contadores do lote em andamento e trava o form (sem barra falsa)", () => {
    m.lotes.mockReturnValue(
      ok({
        items: [lote({ id: "l2", status: "processando", etapa: "Estrutura 2 de 5", estruturas_processadas: 2, estruturas_com_erro: 1 })],
        total: 1,
      }),
    );
    renderPage();
    const bloco = rtl.screen.getByTestId("progresso-lote");
    expect(rtl.within(bloco).getByText("Processando suas Headlines")).toBeTruthy();
    expect(rtl.within(bloco).getByText("Estrutura 2 de 5")).toBeTruthy();
    expect(rtl.within(bloco).getByText(/2 de 5 estruturas processadas · 1 com erro/)).toBeTruthy();
    expect(rtl.screen.getByText(/Já existe uma geração em andamento/)).toBeTruthy();
  });

  it("sem lote em andamento não há bloco de progresso", () => {
    renderPage();
    expect(rtl.screen.queryByTestId("progresso-lote")).toBeNull();
  });

  it("informa honestamente o fallback para os templates do Método Audience", () => {
    m.lotes.mockReturnValue(ok({ items: [lote({ status: "processando", fallback_metodo: true })], total: 1 }));
    renderPage();
    expect(rtl.screen.getByText(/Sem estruturas da biblioteca — usando templates do Método Audience/)).toBeTruthy();
  });
});

describe("histórico", () => {
  it("ver só habilita em completo/falha; status vem do lote", () => {
    m.lotes.mockReturnValue(
      ok({
        items: [lote({ id: "a", status: "completo" }), lote({ id: "b", status: "criando" }), lote({ id: "c", status: "falha" })],
        total: 3,
      }),
    );
    renderPage();
    const ver = (id: string) => rtl.within(rtl.screen.getByTestId(`lote-${id}`)).getByRole("button", { name: /^Ver lote/ }) as HTMLButtonElement;
    expect(ver("a").disabled).toBe(false);
    expect(ver("b").disabled).toBe(true);
    expect(ver("c").disabled).toBe(false);
  });

  it("exclui selecionados depois de confirmar", async () => {
    m.excluir.mockResolvedValue({ excluidos: 1 });
    renderPage();
    await userEvent.click(rtl.screen.getByLabelText(/Selecionar lote de/));
    await userEvent.click(rtl.screen.getByRole("button", { name: /Excluir Selecionados \(1\)/ }));
    await userEvent.click(await rtl.screen.findByRole("button", { name: "Excluir" }));
    await rtl.waitFor(() => expect(m.excluir).toHaveBeenCalledWith(["l1"]));
  });

  it("?lote= abre o resultado do lote, com avisos de poucas estruturas e erros", async () => {
    m.lote.mockReturnValue(
      ok({
        ...lote({ aviso_poucas_estruturas: true, estruturas_com_erro: 2 }),
        parametros: {},
        headlines: [
          {
            id: "h1",
            texto: "Texto da headline",
            favorita: false,
            viral: { id: "v1", codigo: 77, views: 1000, likes: null, score_viral: 2 },
            template_metodo: null,
            itens_usados: [{ slot: "dor", item_id: "i1", conteudo: "Item usado" }],
          },
        ],
      }),
    );
    renderPage("/media-creation/headlines?who=me&lote=l1");
    expect(await rtl.screen.findByText("Headlines Geradas")).toBeTruthy();
    expect(rtl.screen.getByText("Texto da headline")).toBeTruthy();
    expect(rtl.screen.getByText("Item usado")).toBeTruthy();
    expect(rtl.screen.getByRole("button", { name: "Ver estrutura #77" })).toBeTruthy();
    expect(rtl.screen.getByText(/Poucas estruturas compatíveis/)).toBeTruthy();
    expect(rtl.screen.getByText("2 estruturas não puderam ser processadas.")).toBeTruthy();
  });
});

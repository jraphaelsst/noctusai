/** PostCardDialog — states, headline bind/unbind, roteiro modal, caption generation. Hooks mocked. */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  post: vi.fn(),
  atualizar: vi.fn(),
  vincularH: vi.fn(),
  desvincularH: vi.fn(),
  gerar: vi.fn(),
  lista: vi.fn(),
  toastErr: vi.fn(),
  roteiroModal: vi.fn(),
  excluir: vi.fn(),
  mover: vi.fn(),
  setMembros: vi.fn(),
  reprocessar: vi.fn(),
  editarHeadline: vi.fn(),
  headlineCompleta: vi.fn(),
  lotes: vi.fn(),
  stages: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: m.toastErr } }));

const idle = { mutate: vi.fn(), isPending: false };
vi.mock("@/hooks/geracao/useEsteira", () => ({
  ESTEIRA_BASE: "/api/media-creation/esteira",
  usePost: (id: string | null) => m.post(id),
  useAtualizarPost: () => ({ mutate: m.atualizar, isPending: false }),
  useVincularHeadline: () => ({ mutate: m.vincularH, isPending: false }),
  useDesvincularHeadline: () => ({ mutate: m.desvincularH, isPending: false }),
  useVincularRoteiro: () => idle,
  useDesvincularRoteiro: () => idle,
  useGerarLegenda: () => ({ mutate: m.gerar, isPending: false }),
  useExcluirPost: () => ({ mutate: m.excluir, isPending: false }),
  useEquipe: () => ({
    data: [
      { id: "u1", nome: "Ana", ativo: true },
      { id: "u2", nome: "Bia", ativo: true },
    ],
    showSkeleton: false,
    isError: false,
  }),
}));
vi.mock("@/lib/pipelines", () => ({
  esteiraPipeline: {
    useStages: () => m.stages(),
    useMoveCard: () => ({ mutate: m.mover, isPending: false }),
  },
}));

const q = (data: unknown) => ({ data, isPending: false, isFetching: false, isError: false });
vi.mock("@/hooks/geracao/usePostHub", () => ({
  flattenTimeline: () => [],
  postHub: {
    useCardResumo: () => q({ descricao: null }),
    useNotaMutations: () => ({ create: idle }),
    useChecklists: () => q([]),
    useChecklistMutations: () => ({ removeChecklist: idle, addItem: idle, toggleItem: idle, removeItem: idle }),
    useSetMembrosMutation: () => ({ mutate: m.setMembros, isPending: false }),
    useTimeline: () => ({ ...q(undefined), hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() }),
    useDocumentos: () => q([]),
    useTiposDocumento: () => q([]),
    useDocumentoMutations: () => ({ upload: idle, remove: idle, getUrl: idle }),
    useLembretes: () => q([]),
    useLembreteMutations: () => ({ criar: idle, atualizar: idle, remover: idle }),
  },
}));
vi.mock("@/hooks/geracao/useHeadlines", () => ({
  useHeadlinesLista: (_marca: string | null, lista: string) => m.lista(lista),
  useHeadline: (id: string | null) => m.headlineCompleta(id),
  useLotesDoPost: () => m.lotes(),
}));
vi.mock("@/hooks/geracao/useRoteiros", () => ({
  useRoteiros: () => ({ data: { items: [] }, showSkeleton: false, isError: false }),
  useReprocessarRoteiro: () => ({ mutate: m.reprocessar, isPending: false }),
  useRoteiro: () => ({ data: { id: "r1", conteudo: "Cena 1", etapa: null }, showSkeleton: false, isError: false }),
}));
vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useIntegrationAccounts: () => ({ data: [{ id: "c1", account_label: "@marca" }] }),
}));
vi.mock("@/components/geracao/headlines/EditarHeadlineModal", () => ({
  EditarHeadlineModal: (p: any) => {
    m.editarHeadline(p);
    return p.open ? <div>editar-headline</div> : null;
  },
}));
vi.mock("@/components/geracao/esteira/GerarHeadlinesDialog", () => ({
  GerarHeadlinesDialog: (p: any) =>
    p.open ? (
      <div>
        gerar-dialog:{p.postId}:{p.marcaId}
        <button onClick={() => p.onConcluido("l9")}>concluir-lote</button>
      </div>
    ) : null,
}));
vi.mock("@/components/geracao/headlines/HeadlinesGeradasModal", () => ({
  HeadlinesGeradasModal: (p: any) =>
    p.open ? (
      <div>
        lote-aberto:{p.loteId}
        <button onClick={() => p.onUsarNoPost({ id: "hg1" })}>usar-hg1</button>
      </div>
    ) : null,
}));
vi.mock("@/components/geracao/roteiro/EditarRoteiroModal", () => ({ EditarRoteiroModal: () => null }));
vi.mock("@/components/geracao/roteiro/RoteiroAvancadoModal", () => ({
  RoteiroAvancadoModal: (p: any) => {
    m.roteiroModal(p);
    return p.open ? <div>roteiro-modal:{p.postId}</div> : null;
  },
}));

import { PostCardDialog } from "./PostCardDialog";

function postBase(over: Record<string, unknown> = {}) {
  return {
    id: "p1",
    marca_id: "m1",
    marca_nome: "Marca Um",
    titulo: "Reel do café",
    formato: "reel",
    etapa_id: "e1",
    kanban_pos: "1",
    headline: null,
    roteiro: null,
    membros: [],
    gravacao_em: null,
    data_entrega: null,
    entrega_concluida: false,
    postado_em: null,
    motivo_bloqueio: null,
    arquivado: false,
    checklist: { feitos: 0, total: 0 },
    comentarios: 0,
    conta: null,
    legenda: null,
    hashtags: [],
    primeiro_comentario: null,
    links_producao: [],
    permalink: null,
    ig_media_id: null,
    lote_ativo: null,
    created_at: "",
    updated_at: "",
    ...over,
  };
}
const ok = (post: unknown) => ({ data: post, showSkeleton: false, isRefreshing: false, isError: false });
const headline = { id: "h1", texto: "Café muda tudo", favorita: true };
const roteiroOk = { id: "r1", nome: "Roteiro 1", status: "completo", headline_id: "h1", headline_diferente: false };

const tab = (k: string) => fireEvent.click(screen.getByTestId(`card-subpage-tab-${k}`));
const montar = (onClose = vi.fn()) => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <PostCardDialog postId="p1" onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onClose;
};

beforeEach(() => {
  m.post.mockReturnValue(ok(postBase()));
  m.headlineCompleta.mockReturnValue({ data: undefined });
  m.lotes.mockReturnValue({ data: { items: [] }, showSkeleton: false, isError: false });
  m.stages.mockReturnValue({
    data: [
      { id: "e0", label: "Ideia", posicao: 0, papel: null, ativo: true },
      { id: "e1", label: "Roteiro", posicao: 1, papel: null, ativo: true },
      { id: "e2", label: "Gravação", posicao: 2, papel: "gravacao", ativo: true },
      { id: "e3", label: "Postado", posicao: 3, papel: "postado", ativo: true },
      { id: "e4", label: "Cancelado", posicao: 4, papel: "cancelado", ativo: true },
    ],
    isPending: false,
    isError: false,
  });
  m.lista.mockImplementation((lista: string) => ({
    data: {
      items:
        lista === "favoritas"
          ? [
              { id: "h2", texto: "Livre", post: null },
              { id: "h3", texto: "Ocupada", post: { id: "px", titulo: "Outro post", etapa_label: "Ideia" } },
            ]
          : [],
    },
    showSkeleton: false,
    isError: false,
  }));
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PostCardDialog states", () => {
  it("mostra o esqueleto só sem dados", () => {
    m.post.mockReturnValue({ data: undefined, showSkeleton: true, isRefreshing: false, isError: false });
    montar();
    expect(screen.getByTestId("post-card-dialog-loading")).toBeInTheDocument();
  });

  it("refetch mantém o cartão (nunca o esqueleto)", () => {
    m.post.mockReturnValue({ ...ok(postBase()), isRefreshing: true });
    montar();
    expect(screen.queryByTestId("post-card-dialog-loading")).not.toBeInTheDocument();
    expect(screen.getByText("Atualizando…")).toBeInTheDocument();
    expect(screen.getByTestId("secao-geral")).toBeInTheDocument();
  });

  it("erro de carga", () => {
    m.post.mockReturnValue({ data: undefined, showSkeleton: false, isRefreshing: false, isError: true, error: {} });
    montar();
    expect(screen.getByTestId("post-card-dialog-error")).toBeInTheDocument();
  });

  it("404 vira 'não encontrado'", () => {
    m.post.mockReturnValue({
      data: undefined,
      showSkeleton: false,
      isRefreshing: false,
      isError: true,
      error: { status: 404 },
    });
    montar();
    expect(screen.getByTestId("post-card-dialog-not-found")).toBeInTheDocument();
  });

  it("renderiza título, marca e motivo de bloqueio", () => {
    m.post.mockReturnValue(ok(postBase({ motivo_bloqueio: "Falta autorização" })));
    montar();
    expect(screen.getAllByRole("heading", { level: 2, name: "Reel do café" }).length).toBeGreaterThan(0);
    expect(screen.getByTestId("post-marca")).toHaveTextContent("Marca Um");
    expect(screen.getByTestId("motivo-bloqueio")).toHaveTextContent("Falta autorização");
  });

  it("fechar chama onClose", () => {
    const onClose = montar();
    fireEvent.keyDown(screen.getByTestId("post-card-dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Headline", () => {
  it("sem headline: escolher da biblioteca desabilita linhas de outro post e vincula a livre", () => {
    montar();
    tab("headline");
    expect(screen.getByTestId("headline-vazia")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Escolher da biblioteca"));
    expect(screen.getByText("No post: Outro post")).toBeInTheDocument();
    const botoes = screen.getAllByText("Usar neste post");
    expect(botoes[1]).toBeDisabled();
    fireEvent.click(botoes[0]);
    expect(m.vincularH).toHaveBeenCalledWith({ postId: "p1", body: { headline_id: "h2" } }, expect.any(Object));
  });

  it("escrever a minha envia o texto", () => {
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Escrever a minha"));
    fireEvent.change(screen.getByLabelText("Texto da headline"), { target: { value: "  Minha ideia " } });
    fireEvent.click(screen.getByText("Salvar headline"));
    expect(m.vincularH).toHaveBeenCalledWith({ postId: "p1", body: { texto: "Minha ideia" } }, expect.any(Object));
  });

  it("falha ao vincular mostra erro e não fecha em silêncio", () => {
    m.vincularH.mockImplementation((_v: unknown, o: any) => o.onError(new Error("headline_ja_em_post")));
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Escolher da biblioteca"));
    fireEvent.click(screen.getAllByText("Usar neste post")[0]);
    expect(m.toastErr).toHaveBeenCalledWith("headline_ja_em_post");
    expect(screen.getByTestId("headline-picker")).toBeInTheDocument();
  });

  it("lista vazia e erro da lista têm estado próprio", () => {
    m.lista.mockReturnValue({ data: { items: [] }, showSkeleton: false, isError: false });
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Escolher da biblioteca"));
    expect(screen.getByTestId("headline-picker-vazio")).toBeInTheDocument();
    cleanup();
    m.lista.mockReturnValue({ data: undefined, showSkeleton: false, isError: true });
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Escolher da biblioteca"));
    expect(screen.getByTestId("headline-picker-erro")).toBeInTheDocument();
  });

  it("com headline: mostra o texto e desvincula", () => {
    m.post.mockReturnValue(ok(postBase({ headline })));
    montar();
    tab("headline");
    expect(screen.getByTestId("headline-texto")).toHaveTextContent("Café muda tudo");
    fireEvent.click(screen.getByText("Desvincular"));
    expect(m.desvincularH).toHaveBeenCalledWith("p1", expect.any(Object));
  });

  it("lote ativo mostra 'Gerando headlines'", () => {
    m.post.mockReturnValue(ok(postBase({ lote_ativo: { id: "l1", status: "processando", etapa: "Estruturas" } })));
    montar();
    tab("headline");
    expect(screen.getByTestId("headline-gerando")).toHaveTextContent("Gerando headlines: Estruturas");
  });
});

describe("Roteiro", () => {
  it("Criar roteiro abre o modal existente com postId", () => {
    montar();
    tab("roteiro");
    expect(screen.getByTestId("roteiro-vazio")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Criar roteiro"));
    expect(screen.getByText("roteiro-modal:p1")).toBeInTheDocument();
  });
});

describe("Publicação / legenda", () => {
  it("gerar legenda fica desabilitado sem roteiro completo", () => {
    montar();
    tab("publicacao");
    expect(screen.getByText("Gerar legenda com IA")).toBeDisabled();
  });

  it("gerar legenda preenche os campos e NÃO salva", () => {
    m.post.mockReturnValue(ok(postBase({ headline, roteiro: roteiroOk })));
    m.gerar.mockImplementation((_id: string, o: any) =>
      o.onSuccess({ legenda: "Legenda IA", hashtags: ["cafe", "reels"], primeiro_comentario: "Comenta aí" }),
    );
    montar();
    tab("publicacao");
    fireEvent.click(screen.getByText("Gerar legenda com IA"));
    expect(m.gerar).toHaveBeenCalledWith("p1", expect.any(Object));
    expect(screen.getByLabelText("Legenda")).toHaveValue("Legenda IA");
    expect(screen.getByLabelText("Hashtags")).toHaveValue("#cafe #reels");
    expect(screen.getByLabelText("Primeiro comentário")).toHaveValue("Comenta aí");
    expect(m.atualizar).not.toHaveBeenCalled();
  });

  it("falha na geração mostra o erro e não altera os campos", () => {
    m.post.mockReturnValue(ok(postBase({ legenda: "Atual", roteiro: roteiroOk })));
    m.gerar.mockImplementation((_id: string, o: any) => o.onError(new Error("cota diária atingida")));
    montar();
    tab("publicacao");
    fireEvent.click(screen.getByText("Gerar legenda com IA"));
    expect(screen.getByTestId("legenda-erro")).toHaveTextContent("cota diária atingida");
    expect(screen.getByLabelText("Legenda")).toHaveValue("Atual");
  });

  it("Salvar envia legenda, hashtags e primeiro comentário", async () => {
    m.post.mockReturnValue(ok(postBase({ roteiro: roteiroOk })));
    montar();
    tab("publicacao");
    fireEvent.change(screen.getByLabelText("Legenda"), { target: { value: "Texto" } });
    fireEvent.change(screen.getByLabelText("Hashtags"), { target: { value: "#a, b #a" } });
    fireEvent.click(screen.getByText("Salvar"));
    await waitFor(() => expect(m.atualizar).toHaveBeenCalled());
    const arg = m.atualizar.mock.calls[0][0];
    expect(arg.id).toBe("p1");
    expect(arg.patch).toMatchObject({ legenda: "Texto", hashtags: ["a", "b"], primeiro_comentario: null });
  });

  it("legenda acima de 2200 bloqueia o Salvar", () => {
    montar();
    tab("publicacao");
    fireEvent.change(screen.getByLabelText("Legenda"), { target: { value: "x".repeat(2201) } });
    expect(screen.getByText("Salvar")).toBeDisabled();
  });

  it("permalink que não é do instagram bloqueia o Salvar", () => {
    montar();
    tab("publicacao");
    fireEvent.change(screen.getByLabelText("Permalink"), { target: { value: "https://exemplo.com/x" } });
    expect(screen.getByText("Use um link do instagram.com.")).toBeInTheDocument();
    expect(screen.getByText("Salvar")).toBeDisabled();
  });
});

describe("Cabeçalho: título, etapa, membros, menu", () => {
  it("renomeia inline no cabeçalho", () => {
    montar();
    fireEvent.click(screen.getByLabelText("Renomear post"));
    fireEvent.change(screen.getByLabelText("Título do post"), { target: { value: "Novo nome" } });
    fireEvent.click(screen.getByText("Salvar"));
    expect(m.atualizar).toHaveBeenCalledWith({ id: "p1", patch: { titulo: "Novo nome" } }, expect.any(Object));
  });

  it("mover para frente envia direto, sem diálogo", () => {
    montar();
    fireEvent.change(screen.getByLabelText("Etapa"), { target: { value: "e2" } });
    expect(m.mover).toHaveBeenCalledWith({ cardId: "p1", toStageId: "e2" });
  });

  it("voltar pede o motivo antes de enviar (mesma regra do quadro)", async () => {
    m.post.mockReturnValue(ok(postBase({ etapa_id: "e2" })));
    montar();
    fireEvent.change(screen.getByLabelText("Etapa"), { target: { value: "e1" } });
    expect(m.mover).not.toHaveBeenCalled();
    const campo = await screen.findByPlaceholderText("Por que voltar?");
    fireEvent.change(campo, { target: { value: "Faltou cena" } });
    fireEvent.click(screen.getByText("Devolver"));
    expect(m.mover).toHaveBeenCalledWith({ cardId: "p1", toStageId: "e1", motivo: "Faltou cena" });
  });

  it("mover para Postado pede o permalink opcional", async () => {
    m.post.mockReturnValue(ok(postBase({ etapa_id: "e2" })));
    montar();
    fireEvent.change(screen.getByLabelText("Etapa"), { target: { value: "e3" } });
    expect(m.mover).not.toHaveBeenCalled();
    fireEvent.change(await screen.findByPlaceholderText(/instagram.com/), {
      target: { value: "https://www.instagram.com/reel/abc" },
    });
    fireEvent.click(screen.getByText("Confirmar"));
    expect(m.mover).toHaveBeenCalledWith({
      cardId: "p1",
      toStageId: "e3",
      extra: { permalink: "https://www.instagram.com/reel/abc" },
    });
  });

  it("etapas indisponíveis mostram erro, sem select", () => {
    m.stages.mockReturnValue({ data: undefined, isPending: false, isError: true });
    montar();
    expect(screen.getByTestId("etapa-erro")).toBeInTheDocument();
    expect(screen.queryByLabelText("Etapa")).not.toBeInTheDocument();
  });

  it("membros: o popover do seed alterna e envia a lista inteira", async () => {
    m.post.mockReturnValue(ok(postBase({ membros: [{ id: "u1", nome: "Ana", cor: null }] })));
    montar();
    fireEvent.click(screen.getByTestId("membros-trigger"));
    fireEvent.click(await screen.findByTestId("membro-item-u2"));
    expect(m.setMembros).toHaveBeenCalledWith(["u1", "u2"], expect.any(Object));
  });

  it("arquivar pede confirmação", async () => {
    montar();
    fireEvent.pointerDown(screen.getByLabelText("Mais ações"), { button: 0, ctrlKey: false });
    fireEvent.click(await screen.findByText("Arquivar"));
    expect(m.atualizar).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByText("Confirmar"));
    expect(m.atualizar).toHaveBeenCalledWith({ id: "p1", patch: { arquivado: true } }, expect.any(Object));
  });

  it("excluir pede confirmação e fecha o cartão ao concluir", async () => {
    m.excluir.mockImplementation((_id: string, o: any) => o.onSuccess());
    const onClose = montar();
    fireEvent.pointerDown(screen.getByLabelText("Mais ações"), { button: 0, ctrlKey: false });
    fireEvent.click(await screen.findByText("Excluir"));
    expect(m.excluir).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Excluir" }));
    expect(m.excluir).toHaveBeenCalledWith("p1", expect.any(Object));
    expect(onClose).toHaveBeenCalled();
  });

  it("falha ao excluir mostra o erro e mantém o cartão aberto", async () => {
    m.excluir.mockImplementation((_id: string, o: any) => o.onError(new Error("sem permissão")));
    const onClose = montar();
    fireEvent.pointerDown(screen.getByLabelText("Mais ações"), { button: 0, ctrlKey: false });
    fireEvent.click(await screen.findByText("Excluir"));
    fireEvent.click(await screen.findByRole("button", { name: "Excluir" }));
    expect(m.toastErr).toHaveBeenCalledWith("sem permissão");
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("Headline: gerar, recentes e original", () => {
  it("Gerar headlines abre o diálogo com a marca e o post fixos", () => {
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Gerar headlines"));
    expect(screen.getByText("gerar-dialog:p1:m1")).toBeInTheDocument();
  });

  it("ao concluir o lote mostra as headlines e 'Usar neste post' vincula", () => {
    m.vincularH.mockImplementation((_v: unknown, o: any) => o.onSuccess());
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Gerar headlines"));
    fireEvent.click(screen.getByText("concluir-lote"));
    expect(screen.getByText("lote-aberto:l9")).toBeInTheDocument();
    fireEvent.click(screen.getByText("usar-hg1"));
    expect(m.vincularH).toHaveBeenCalledWith({ postId: "p1", body: { headline_id: "hg1" } }, expect.any(Object));
    expect(screen.queryByText(/lote-aberto/)).not.toBeInTheDocument();
  });

  it("aba 'Geradas recentemente' lista os lotes do post e abre o lote", () => {
    m.lotes.mockReturnValue({
      data: { items: [{ id: "l1", resumo: "10 headlines", status: "completo" }] },
      showSkeleton: false,
      isError: false,
    });
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Escolher da biblioteca"));
    fireEvent.click(screen.getByText("Geradas recentemente"));
    fireEvent.click(screen.getByText("Ver headlines"));
    expect(screen.getByText("lote-aberto:l1")).toBeInTheDocument();
  });

  it("aba recentes: vazio e erro", () => {
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Escolher da biblioteca"));
    fireEvent.click(screen.getByText("Geradas recentemente"));
    expect(screen.getByTestId("headline-picker-vazio")).toBeInTheDocument();
    cleanup();
    m.lotes.mockReturnValue({ data: undefined, showSkeleton: false, isError: true });
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Escolher da biblioteca"));
    fireEvent.click(screen.getByText("Geradas recentemente"));
    expect(screen.getByTestId("headline-picker-erro")).toBeInTheDocument();
  });

  it("Editar passa o texto_original REAL (nunca null) ao modal", () => {
    m.post.mockReturnValue(ok(postBase({ headline })));
    m.headlineCompleta.mockReturnValue({ data: { id: "h1", texto_original: "Original da IA" } });
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Editar"));
    const abertas = m.editarHeadline.mock.calls.map((c) => c[0]).filter((p) => p.open);
    expect(abertas.at(-1).headline).toEqual({ id: "h1", texto: "Café muda tudo", texto_original: "Original da IA" });
    expect(m.headlineCompleta).toHaveBeenCalledWith("h1");
  });

  it("antes de carregar a linha real, o original não vira null", () => {
    m.post.mockReturnValue(ok(postBase({ headline })));
    montar();
    tab("headline");
    fireEvent.click(screen.getByText("Editar"));
    const abertas = m.editarHeadline.mock.calls.map((c) => c[0]).filter((p) => p.open);
    expect(abertas.at(-1).headline.texto_original).not.toBeNull();
  });
});

describe("Roteiro: reprocessar", () => {
  it("confirma e reprocessa o roteiro vinculado", () => {
    m.post.mockReturnValue(ok(postBase({ headline, roteiro: roteiroOk })));
    montar();
    tab("roteiro");
    fireEvent.click(screen.getByText("Reprocessar"));
    fireEvent.change(screen.getByLabelText("Informações adicionais"), { target: { value: "mais curto" } });
    fireEvent.click(within(screen.getByTestId("reprocessar-roteiro")).getByText("Reprocessar"));
    expect(m.reprocessar).toHaveBeenCalledWith({ id: "r1", instrucoes_adicionais: "mais curto" }, expect.any(Object));
  });

  it("falha ao reprocessar mostra o erro", () => {
    m.reprocessar.mockImplementation((_v: unknown, o: any) => o.onError(new Error("cota")));
    m.post.mockReturnValue(ok(postBase({ headline, roteiro: roteiroOk })));
    montar();
    tab("roteiro");
    fireEvent.click(screen.getByText("Reprocessar"));
    fireEvent.click(within(screen.getByTestId("reprocessar-roteiro")).getByText("Reprocessar"));
    expect(m.toastErr).toHaveBeenCalledWith("cota");
  });
});

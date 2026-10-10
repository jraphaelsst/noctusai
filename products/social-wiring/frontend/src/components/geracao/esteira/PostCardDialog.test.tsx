/** PostCardDialog — states, headline bind/unbind, roteiro modal, caption generation. Hooks mocked. */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  useEquipe: () => ({ data: [], showSkeleton: false, isError: false }),
}));

const q = (data: unknown) => ({ data, isPending: false, isFetching: false, isError: false });
vi.mock("@/hooks/geracao/usePostHub", () => ({
  flattenTimeline: () => [],
  useDatasPost: () => idle,
  postHub: {
    useCardResumo: () => q({ descricao: null }),
    useNotaMutations: () => ({ create: idle }),
    useChecklists: () => q([]),
    useChecklistMutations: () => ({ removeChecklist: idle, addItem: idle, toggleItem: idle, removeItem: idle }),
    useSetMembrosMutation: () => idle,
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
}));
vi.mock("@/hooks/geracao/useRoteiros", () => ({
  useRoteiros: () => ({ data: { items: [] }, showSkeleton: false, isError: false }),
  useRoteiro: () => ({ data: { id: "r1", conteudo: "Cena 1", etapa: null }, showSkeleton: false, isError: false }),
}));
vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useIntegrationAccounts: () => ({ data: [{ id: "c1", account_label: "@marca" }] }),
}));
vi.mock("@/components/geracao/headlines/EditarHeadlineModal", () => ({ EditarHeadlineModal: () => null }));
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
    expect(screen.getByLabelText("Título do post")).toHaveValue("Reel do café");
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

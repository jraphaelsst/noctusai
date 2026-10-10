/**
 * EsteiraBoard — rendering, orphan bucket, empty/error/loading states, card click,
 * and the move flow (reason / permalink dialogs → the real `mover-etapa` POST).
 * `PipelineBoard` is stubbed with a one-button drop (dnd-kit needs layout jsdom lacks —
 * same approach as the seed's PipelineBoard.moveIntercept test); the stub drives the
 * REAL `onBeforeMove` + `hooks.useMoveCard` the component hands it. API mocked.
 */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  seedApi: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  libApi: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
  drop: { fromId: "", toId: "", direction: "forward" as "forward" | "backward" | "same" },
  props: { current: null as any },
}));

vi.mock("@noctusai/seed/infra", () => ({ api: m.seedApi }));
vi.mock("@/lib/api", () => ({ api: m.libApi }));
vi.mock("sonner", () => ({ toast: m.toast }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({
  ...(await orig<object>()),
  useIsOrgAdmin: () => true,
}));
vi.mock("@noctusai/lib/components", async (orig) => {
  const actual = await orig<any>();
  return {
    ...actual,
    PipelineBoard: (props: any) => {
      m.props.current = props;
      const { data: colunas } = props.hooks.useBoard(props.filtros);
      const move = props.hooks.useMoveCard({ onError: props.onMoveError });
      const cols: any[] = colunas ?? [];
      return (
        <div>
          {cols.flatMap((c) => c.cards).map((card) => (
            <div key={card.id}>{props.renderCard(card, { isDragging: false })}</div>
          ))}
          <button
            onClick={async () => {
              const from = cols.find((c) => c.etapa === m.drop.fromId).stage;
              const to = cols.find((c) => c.etapa === m.drop.toId).stage;
              const decisao = await props.onBeforeMove({
                card: cols[0].cards[0],
                fromStage: from,
                toStage: to,
                toIndex: 0,
                direction: m.drop.direction,
                stepDistance: 1,
              });
              if (decisao === false) return;
              const d = decisao === true ? {} : decisao;
              move.mutate({ cardId: "p1", toStageId: m.drop.toId, toIndex: 0, ...d });
            }}
          >
            soltar
          </button>
        </div>
      );
    },
  };
});

import { EsteiraBoard } from "./EsteiraBoard";

const stage = (id: string, posicao: number, papel: string | null = null) => ({
  id,
  slug: id,
  label: id.toUpperCase(),
  cor: "secondary",
  posicao,
  papel,
  ativo: true,
});
const post = (over: Record<string, unknown> = {}) => ({
  id: "p1",
  marca_id: "m1",
  marca_nome: "Marca Um",
  titulo: "Reel do café",
  formato: "reel",
  etapa_id: "ideia",
  kanban_pos: "1",
  headline: { id: "h1", texto: "Café muda tudo", favorita: true },
  roteiro: { id: "r1", nome: "R", status: "completo", headline_id: "h1", headline_diferente: false },
  membros: [{ id: "u1", nome: "Ana", cor: null }],
  gravacao_em: null,
  data_entrega: null,
  entrega_concluida: false,
  postado_em: null,
  motivo_bloqueio: null,
  arquivado: false,
  checklist: { feitos: 1, total: 3 },
  comentarios: 2,
  ...over,
});
const board = (orfaos = 0, cards = [post()]) => ({
  data: {
    colunas: [
      { etapa: "ideia", stage: stage("ideia", 0), cards, total: cards.length, exibidos: cards.length },
      { etapa: "gravacao", stage: stage("gravacao", 1, "gravacao"), cards: [], total: 0, exibidos: 0 },
      { etapa: "postado", stage: stage("postado", 2, "postado"), cards: [], total: 0, exibidos: 0 },
      { etapa: "cancelado", stage: stage("cancelado", 3, "cancelado"), cards: [], total: 0, exibidos: 0 },
    ],
    orfaos,
  },
});

let qc: QueryClient;
function montar(filtros = {}, onOpenPost = vi.fn()) {
  render(
    <QueryClientProvider client={qc}>
      <EsteiraBoard filtros={filtros} onOpenPost={onOpenPost} />
    </QueryClientProvider>,
  );
  return onOpenPost;
}

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  m.libApi.post.mockResolvedValue({ data: post() });
});
afterEach(() => {
  cleanup();
  Object.values(m.seedApi).forEach((f) => f.mockReset());
  Object.values(m.libApi).forEach((f) => f.mockReset());
  m.toast.error.mockReset();
});

describe("EsteiraBoard", () => {
  it("mostra skeleton só no primeiro carregamento e depois o card", async () => {
    m.seedApi.get.mockResolvedValue(board());
    montar();
    expect(screen.getByTestId("esteira-skeleton")).toBeInTheDocument();
    expect(await screen.findByText("Reel do café")).toBeInTheDocument();
    expect(screen.queryByTestId("esteira-skeleton")).toBeNull();
    expect(screen.getByText("Café muda tudo")).toBeInTheDocument();
    expect(screen.getByText("Marca Um")).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
  });

  it("passa roleLabels, showValue=false e envia os filtros ao /board", async () => {
    m.seedApi.get.mockResolvedValue(board());
    montar({ marca_id: "m1", busca: "café" });
    await screen.findByText("Reel do café");
    expect(m.props.current.showValue).toBe(false);
    expect(m.props.current.roleLabels).toEqual({
      gravacao: "Início da produção",
      postado: "Publicado",
      cancelado: "Encerrado",
    });
    expect(m.seedApi.get).toHaveBeenCalledWith("/api/media-creation/esteira/board?marca_id=m1&busca=caf%C3%A9");
    // marca chip hidden when filtering by one marca
    expect(screen.queryByText("Marca Um")).toBeNull();
  });

  it("clicar no card chama onOpenPost(id)", async () => {
    m.seedApi.get.mockResolvedValue(board());
    const onOpen = montar();
    fireEvent.click(await screen.findByTestId("post-card-p1"));
    expect(onOpen).toHaveBeenCalledWith("p1");
  });

  it("mostra o balde de órfãos", async () => {
    m.seedApi.get.mockResolvedValue(board(2));
    montar();
    expect(await screen.findByTestId("esteira-orfaos")).toHaveTextContent("2 posts estão em etapas removidas");
  });

  it("board vazio mostra a mensagem de vazio (e nada de órfãos)", async () => {
    m.seedApi.get.mockResolvedValue(board(0, []));
    montar();
    expect(await screen.findByTestId("esteira-vazio")).toHaveTextContent("Nenhum post ainda");
    expect(screen.queryByTestId("esteira-orfaos")).toBeNull();
  });

  it("erro na primeira carga mostra alerta e tenta de novo", async () => {
    m.seedApi.get.mockRejectedValueOnce(new Error("[500] falhou")).mockResolvedValue(board());
    montar();
    expect(await screen.findByRole("alert")).toHaveTextContent("falhou");
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(await screen.findByText("Reel do café")).toBeInTheDocument();
  });

  it("avanço livre (vários passos) não pede nada e faz o POST mover-etapa", async () => {
    m.seedApi.get.mockResolvedValue(board());
    m.drop.fromId = "ideia";
    m.drop.toId = "gravacao";
    m.drop.direction = "forward";
    montar();
    fireEvent.click(await screen.findByText("soltar"));
    await waitFor(() =>
      expect(m.libApi.post).toHaveBeenCalledWith("/api/media-creation/esteira/posts/p1/mover-etapa", {
        para_etapa_id: "gravacao",
        novo_indice: 0,
        motivo: undefined,
      }),
    );
  });

  it("voltar exige motivo e o envia", async () => {
    m.seedApi.get.mockResolvedValue(board());
    m.drop.fromId = "gravacao";
    m.drop.toId = "ideia";
    m.drop.direction = "backward";
    montar();
    fireEvent.click(await screen.findByText("soltar"));
    await userEvent.type(await screen.findByPlaceholderText("Por que voltar?"), "ajustar roteiro");
    fireEvent.click(screen.getByText("Devolver"));
    await waitFor(() =>
      expect(m.libApi.post).toHaveBeenCalledWith(
        "/api/media-creation/esteira/posts/p1/mover-etapa",
        expect.objectContaining({ para_etapa_id: "ideia", motivo: "ajustar roteiro" }),
      ),
    );
  });

  it("cancelar o diálogo de motivo não envia nada", async () => {
    m.seedApi.get.mockResolvedValue(board());
    m.drop.fromId = "ideia";
    m.drop.toId = "cancelado";
    m.drop.direction = "forward";
    montar();
    fireEvent.click(await screen.findByText("soltar"));
    expect(await screen.findByText("Motivo do bloqueio ou cancelamento")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Cancelar"));
    await waitFor(() => expect(screen.queryByText("Motivo do bloqueio ou cancelamento")).toBeNull());
    expect(m.libApi.post).not.toHaveBeenCalled();
  });

  it("mover para postado envia o permalink opcional", async () => {
    m.seedApi.get.mockResolvedValue(board());
    m.drop.fromId = "ideia";
    m.drop.toId = "postado";
    m.drop.direction = "forward";
    montar();
    fireEvent.click(await screen.findByText("soltar"));
    await userEvent.type(
      await screen.findByPlaceholderText("https://www.instagram.com/reel/..."),
      "https://www.instagram.com/reel/abc/",
    );
    fireEvent.click(screen.getByText("Confirmar"));
    await waitFor(() =>
      expect(m.libApi.post).toHaveBeenCalledWith(
        "/api/media-creation/esteira/posts/p1/mover-etapa",
        expect.objectContaining({ permalink: "https://www.instagram.com/reel/abc/" }),
      ),
    );
  });

  it("409 pendencias vira toast com 'Abrir post'", async () => {
    m.seedApi.get.mockResolvedValue(board());
    m.libApi.post.mockRejectedValue(Object.assign(new Error("[409] x"), { body: { code: "pendencias" } }));
    m.drop.fromId = "ideia";
    m.drop.toId = "gravacao";
    m.drop.direction = "forward";
    const onOpen = montar();
    fireEvent.click(await screen.findByText("soltar"));
    await waitFor(() => expect(m.toast.error).toHaveBeenCalled());
    const [msg, opts] = m.toast.error.mock.calls[0];
    expect(msg).toMatch(/headline e roteiro concluído/);
    opts.action.onClick();
    expect(onOpen).toHaveBeenCalledWith("p1");
  });
});

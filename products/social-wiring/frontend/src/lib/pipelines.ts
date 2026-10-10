/**
 * social-wiring's two pipelines, declared once.
 *
 * This file is the entire frontend surface of the Funil de Vendas and
 * Processos de Venda boards — the board query, the optimistic move with
 * rollback, the column totals and the stage editor all come from
 * `@noctusai/lib`'s `createPipelineHooks` / `PipelineBoard`, shared with
 * erp-imobiliario.
 */
import { api } from "@/lib/api";
import { createPipelineHooks } from "@noctusai/lib/components";

import { ESTEIRA_PIPELINE_KEY } from "@/lib/esteiraKeys";
import type { PostCard } from "@/types/esteira";
import type { Atendimento, ProcessoVenda } from "@/types/pipeline";

/**
 * Funil de Vendas.
 *
 * `boardEndpoint` and `moveEndpoint` differ because the board is a VIEW
 * (`/api/funil`) while the card is a RESOURCE (`/api/atendimentos-venda`).
 */
export const funilPipeline = createPipelineHooks<Atendimento>(
  {
    queryKey: "sw-funil",
    boardEndpoint: "/api/funil",
    stagesEndpoint: "/api/funil/etapas",
    moveEndpoint: "/api/atendimentos-venda",
    getCardId: (n) => n.id,
    getCardValue: (n) => Number(n.valor_estimado || 0),
    entityLabel: "negociação",
    // Accepting a proposal moves the deal onto the other board, and the Leads
    // surface shows lead state that a funnel action can change.
    invalidateOnSettle: ["sw-processos", "atendimentos-venda", "leads"],
  },
  api,
);

/** Processos de Venda — post-acceptance delivery. */
export const processosPipeline = createPipelineHooks<ProcessoVenda>(
  {
    queryKey: "sw-processos",
    boardEndpoint: "/api/processos-venda",
    stagesEndpoint: "/api/processos-venda/etapas",
    moveEndpoint: "/api/processos-venda",
    getCardId: (p) => p.id,
    getCardValue: (p) => Number(p.valor || 0),
    entityLabel: "processo",
  },
  api,
);

/**
 * Esteira de Reels (Core Studio). The board is a VIEW (`/esteira/board`), the
 * card a RESOURCE (`/esteira/posts`); stage CRUD is the seed
 * `pipeline_stages_router` at `/esteira/etapas`.
 *
 * The contract's board payload is `{colunas, orfaos}`, not a bare
 * `PipelineColumn[]`, so the board is read by `useEsteiraBoard`
 * (hooks/geracao/useEsteira.ts), which stores the unwrapped `colunas` under
 * this descriptor's key so `useMoveCard`'s optimistic splice keeps working.
 * Take `useStages` / `useMoveCard` / stage CRUD from here, not `useBoard`.
 */
export const esteiraPipeline = createPipelineHooks<PostCard>(
  {
    queryKey: ESTEIRA_PIPELINE_KEY,
    boardEndpoint: "/api/media-creation/esteira/board",
    stagesEndpoint: "/api/media-creation/esteira/etapas",
    moveEndpoint: "/api/media-creation/esteira/posts",
    getCardId: (p) => p.id,
    getCardValue: () => 0,
    entityLabel: "post",
    // A move changes the post detail, and the Geração libraries show the
    // post badge (`etapa_label`).
    invalidateOnSettle: ["sw"],
  },
  api,
);

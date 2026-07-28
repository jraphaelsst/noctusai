/**
 * The ERP's two pipelines, declared once and consumed by both pages.
 *
 * This file is the entire frontend difference between the Funil de Vendas board
 * and the Processos de Venda board. Everything else — the board query, the
 * optimistic move, the stage editor, the column headers — is
 * `@noctusai/lib/components`.
 *
 * What it REPLACES: `hooks/useFunil.ts` and `hooks/useProcessos.ts` each
 * carried their own copy of the same optimistic-move mutation (~60 lines,
 * identical but for the query key, endpoint, id field and value field), plus
 * `lib/etapasConfig.ts` / `lib/etapasProcessoConfig.ts`, which hardcoded the
 * stage vocabulary that is now per-organization DB rows.
 */
import { api } from '@noctusai/seed/infra';
import { createPipelineHooks } from '@noctusai/lib/components';

import type { NegociacaoVenda } from '@/types/negociacoes';
import type { ProcessoVenda } from '@/types/processos';

/**
 * Funil de Vendas.
 *
 * `boardEndpoint` and `moveEndpoint` differ on purpose: the board is a VIEW
 * (`/api/funil`) while the card is a RESOURCE (`/api/negociacoes-venda`), and
 * the move acts on the resource.
 */
export const funilPipeline = createPipelineHooks<NegociacaoVenda>(
  {
    queryKey: 'funil',
    boardEndpoint: '/api/funil',
    stagesEndpoint: '/api/funil/etapas',
    moveEndpoint: '/api/negociacoes-venda',
    getCardId: (n) => n.id,
    getCardValue: (n) => Number(n.valor_estimado || 0),
    entityLabel: 'negociação',
    // A deal accepted from the Funil becomes a processo; the other board is
    // stale the moment this one changes.
    invalidateOnSettle: ['clientes', 'processos-venda'],
  },
  api,
);

/** Processos de Venda — the post-proposal execution board. */
export const processosPipeline = createPipelineHooks<ProcessoVenda>(
  {
    queryKey: 'processos-venda',
    boardEndpoint: '/api/processos-venda',
    stagesEndpoint: '/api/processos-venda/etapas',
    moveEndpoint: '/api/processos-venda',
    getCardId: (p) => p.id,
    getCardValue: (p) => Number(p.valor || 0),
    entityLabel: 'processo',
  },
  api,
);

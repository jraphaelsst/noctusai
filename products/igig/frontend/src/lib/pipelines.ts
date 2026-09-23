/**
 * igig's Comercial funnel, declared once (wave-2 contract, Slice C).
 *
 * The board query, the optimistic move with rollback, column totals and the
 * in-header stage editor all come from `@noctusai/lib`'s `createPipelineHooks`
 * / `PipelineBoard` — the same organ erp-imobiliario and social-wiring run.
 * `boardEndpoint` is a VIEW (`/api/comercial/board`); the card is a RESOURCE
 * (`/api/comercial/negocios`), hence the separate `moveEndpoint`.
 */
import { createPipelineHooks } from "@noctusai/lib/components";

import { api } from "@/lib/api";
import type { Negocio } from "@/types/crm";

export const COMERCIAL_BOARD_KEY = "igig-comercial";

/** The stage role whose entry closes the deal and REQUIRES an orçamento (R4). */
export const PAPEL_FECHADO = "fechado";

export const comercialPipeline = createPipelineHooks<Negocio>(
  {
    queryKey: COMERCIAL_BOARD_KEY,
    boardEndpoint: "/api/comercial/board",
    stagesEndpoint: "/api/comercial/pipeline/stages",
    moveEndpoint: "/api/comercial/negocios",
    getCardId: (n) => n.id,
    getCardValue: (n) => Number(n.valor_estimado || 0),
    entityLabel: "negócio",
    // A close accepts an orçamento and creates a Cliente.
    invalidateOnSettle: ["igig"],
  },
  api,
);

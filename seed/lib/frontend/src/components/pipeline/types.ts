/**
 * Types for the pipeline mechanic — the data half of the kanban organ.
 *
 * `KanbanBoard` (sibling folder) owns PRESENTATION: columns, drag, overlay.
 * This module owns the MECHANIC: fetching the board, fetching and editing the
 * stage definitions, and moving a card with an optimistic update.
 *
 * They are separate because the ERP proved you can want one without the other —
 * orbity's Funil consumes the board organ but keeps its own data layer. A
 * consumer takes `PipelineBoard` (both halves) or `KanbanBoard` (presentation
 * only).
 */

/** A stage row. `id` is what cards reference; `label` is what humans edit. */
export interface PipelineStage {
  id: string;
  slug: string;
  label: string;
  cor: StageColor;
  posicao: number;
  /**
   * Semantic role the CODE keys on, so features survive a rename:
   * - `proposta_aceite` — the stage a proposal may be accepted from
   * - `final` — the pipeline's terminal stage
   */
  papel: StageRole | null;
  ativo: boolean;
}

export type StageColor =
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'destructive'
  | 'muted';

export type StageRole = 'proposta_aceite' | 'final';

/** One column as the board endpoint returns it. */
export interface PipelineColumn<TCard> {
  /** The stage ID. Kept named `etapa` for wire-compatibility with the ERP. */
  etapa: string;
  stage: PipelineStage;
  total: number;
  valorTotal: number;
  cards: TCard[];
}

/** The minimal API surface the hooks need, injected by the product. */
export interface PipelineApi {
  get: <T = any>(path: string, params?: Record<string, any>) => Promise<T>;
  post: <T = any>(path: string, body?: unknown) => Promise<T>;
  patch: <T = any>(path: string, body?: unknown) => Promise<T>;
  delete: <T = any>(path: string, params?: Record<string, any>) => Promise<T>;
}

/**
 * Everything a consumer declares to get a working, editable board.
 *
 * This is the "one component, dynamically populated" contract: two boards
 * differ by a literal of this shape and nothing else.
 */
export interface PipelineDescriptor<TCard> {
  /** React Query key root. Must be unique per board. */
  queryKey: string;
  /** Board endpoint, e.g. `/api/funil`. Returns `PipelineColumn[]`. */
  boardEndpoint: string;
  /**
   * Stage CRUD endpoint, e.g. `/api/funil/etapas`.
   * Omit to render a read-only board with no stage editor.
   */
  stagesEndpoint?: string;
  /**
   * Where a move is POSTed: `${moveEndpoint}/${cardId}/mover-etapa`.
   *
   * Separate from `boardEndpoint` because the two genuinely differ — the ERP
   * Funil reads from `/api/funil` but moves via `/api/negociacoes-venda`, since
   * the board is a view and the card is the resource.
   */
  moveEndpoint: string;
  /** Card identity + placement accessors. */
  getCardId: (card: TCard) => string;
  /** Monetary value for the column total. */
  getCardValue: (card: TCard) => number;
  /** Noun for toasts/messages, e.g. "negociação". */
  entityLabel: string;
  /** Extra query keys to invalidate after a mutation settles. */
  invalidateOnSettle?: string[];
}

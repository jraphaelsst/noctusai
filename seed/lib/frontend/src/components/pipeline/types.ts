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
   * Semantic role the CODE keys on, so features survive a rename. The default
   * set (seed `PipelineConfig.stage_roles`):
   * - `proposta_aceite` — the stage a proposal may be accepted from
   * - `final` — the pipeline's terminal stage
   * A board may declare its own roles server-side; see `StageRole`.
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

/**
 * A stage's semantic role. OPEN: the set is declared per pipeline by the
 * backend (`PipelineConfig.stage_roles`, served at `GET <stages>/opcoes`), so
 * the frontend cannot close it. The two default roles stay spelled out for
 * editor autocompletion; `(string & {})` keeps any other string assignable
 * without collapsing the union to plain `string`. Human labels come from a
 * `roleLabels` descriptor (default `STAGE_ROLE_LABELS`), never from here.
 */
export type StageRole = DefaultStageRole | (string & {});

/** The roles every pipeline has unless it declares its own. */
export type DefaultStageRole = 'proposta_aceite' | 'final';

/** Role → human label. Unknown roles render as the raw role string. */
export type StageRoleLabels = Record<string, string>;

/** One column as the board endpoint returns it. */
export interface PipelineColumn<TCard> {
  /**
   * How many of `total` this response actually carries.
   *
   * A board may cap the cards it sends per column (social-wiring's funil holds
   * 1.070 in one stage). `total` stays the true count and `valorTotal` still
   * covers all of it — this is the only field that says the card LIST is
   * short. Absent means "everything was sent".
   */
  exibidos?: number;
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

/**
 * What `PipelineBoard`'s `onBeforeMove` returns:
 *  - `false` — cancel. The card was never optimistically moved (see
 *    `MoveIntentContext` doc), so cancelling is a no-op on the cache — the
 *    board just re-renders in its unchanged state.
 *  - `true` — proceed exactly as dropped, no `motivo`/`extra`.
 *  - `{ motivo?, extra? }` — proceed, merging both into the `MoveVariables`
 *    the mutation sends (`extra` is spread into the `mover-etapa` POST body).
 */
export type MoveDecision = false | true | { motivo?: string; extra?: Record<string, unknown> };

/**
 * Everything `PipelineBoard`'s `onBeforeMove` needs to decide whether a drag
 * may proceed.
 */
export interface MoveIntentContext<TCard> {
  card: TCard;
  fromStage: PipelineStage;
  toStage: PipelineStage;
  toIndex: number;
  /**
   * Derived from the board's CURRENT column order (left→right), not the
   * stages' raw `posicao` — a hidden/inactive stage sitting between two
   * visible ones would otherwise inflate `stepDistance` for a move that
   * looks adjacent on screen.
   */
  direction: 'forward' | 'backward' | 'same';
  /** How many columns apart `fromStage` and `toStage` are, in display order. */
  stepDistance: number;
}

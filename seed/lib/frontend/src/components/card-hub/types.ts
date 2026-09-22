/**
 * Card-hub contract types — the GENERIC slice of social-wiring's
 * `products/social-wiring/frontend/src/types/cardHub.ts`, moved (not
 * rewritten) per `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * §1/§2. Every shape here is entity-agnostic: a "card" is any record a
 * product mounts the card hub on (SW: a cliente; igig: a lead). The entity
 * itself and every product-only relation (SW: compradores, roteiros,
 * agendamentos, documento-checklist) stay in the product and EXTEND these.
 *
 * Wire shapes mirror the seed backend module
 * `noctusai_lib.domain.card_hub` (Slice A) — keep the two in step.
 */

// ─── Ator / person references ──────────────────────────────────────────────

export interface AtorRef {
  id: string;
  nome: string;
}

// ─── Tags (D6 — one system) ─────────────────────────────────────────────────

export interface Tag {
  id: string;
  nome: string;
  /** Hex colour, e.g. `#eb5a46`. */
  cor: string;
}

// ─── Membros (D10 — points at lead_corretores, never a name) ───────────────

export interface Membro {
  id: string;
  nome: string;
  /** `lead_corretores.cor`, when set — optional avatar accent. */
  cor?: string | null;
}

// ─── Notas ───────────────────────────────────────────────────────────────

export type NotaTipo = "descricao" | "comentario";

export interface Nota {
  id: string;
  /**
   * Backend correction (`card_hub/schemas.py::NotaCreateBody`, landed on
   * `origin/dev`): Descrição (one per card) and Comentários (many,
   * chronological) are distinct Trello concepts `cliente_notas` was
   * originally going to conflate — `tipo` is the real discriminator.
   * Defaults to `"comentario"` server-side when omitted on create.
   */
  tipo: NotaTipo;
  corpo: string;
  /** `null` when the author id didn't resolve to a known user (`_actor()`). */
  autor: AtorRef | null;
  /** `null` ⇒ never edited. */
  editado_em: string | null;
  /** Soft-delete tombstone — a deleted note still occupies its timeline slot. */
  deleted_at: string | null;
}

/**
 * The card's single `tipo='descricao'` note (`GET /clientes/{id}/card`'s
 * `descricao` field) — a NARROWER shape than `Nota`: no `autor`/`tipo`/
 * `deleted_at`, per `card_hub/services.py::get_descricao`'s own docstring
 * ("never the autor/deleted_at shape `_nota_out` returns for comentários").
 * `null` when the card has no description yet.
 */
export interface Descricao {
  id: string;
  corpo: string;
  editado_em: string | null;
}

// ─── Datas + lembretes (screenshot 06) ─────────────────────────────────────

export type Recorrencia = "diaria" | "semanal" | "mensal" | "anual" | null;

export interface ProximoLembrete {
  id: string;
  dispara_em: string;
}

export interface CardDatas {
  data_inicio: string | null;
  data_entrega: string | null;
  entrega_concluida: boolean;
  lembrete_minutos_antes: number | null;
  recorrencia: Recorrencia;
}

export interface DatasPatchResponse extends CardDatas {
  /**
   * `null` when no reminder is materialised — either none was requested, or
   * (§3) the delivery path is not wired this slice and the endpoint says so
   * honestly rather than accepting the value silently.
   */
  proximo_lembrete: ProximoLembrete | null;
}

export interface DatasPatchBody {
  data_inicio?: string | null;
  data_entrega?: string | null;
  entrega_concluida?: boolean;
  lembrete_minutos_antes?: number | null;
  recorrencia?: Recorrencia;
}

// ─── Checklists (D11 — both halves) ────────────────────────────────────────

export type ChecklistOrigem = "ad_hoc" | "etapa";

export interface ChecklistItem {
  id: string;
  texto: string;
  concluido: boolean;
  concluido_em: string | null;
  concluido_por: string | null;
  posicao: number;
}

export interface Checklist {
  id: string;
  titulo: string;
  posicao: number;
  origem: ChecklistOrigem;
  etapa_id: string | null;
  itens: ChecklistItem[];
  /** Served, not counted client-side — §3. */
  total_itens: number;
  concluidos: number;
}

// ─── Documentos (LGPD, D5) ──────────────────────────────────────────────────

export interface Documento {
  id: string;
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
  tipo_documento: string;
  categoria_lgpd: string;
  retencao_ate: string | null;
  enviado_por: AtorRef;
  created_at: string;
  thumbnail_url: string | null;
  /**
   * `null` for a type `identidade_extracao_service.deve_extrair` never
   * reads (a `contrato`, a `foto_imovel`) — the honest value, not a gap.
   * `"pendente" | "processando"` while a read is queued/in flight,
   * `"ok" | "sem_dados"` on a terminal success, `"erro"` on a terminal
   * failure (see `extracao_erro` for why).
   */
  extracao_status: string | null;
  /** The human-readable failure reason, set only when `extracao_status ===
   *  "erro"`. `POST .../documentos/{id}/extrair` clears both together. */
  extracao_erro: string | null;
}

/**
 * `card_hub/documentos_service.py::list_tipos_documento` — the real shape
 * (corrects this file's earlier ASSUMPTION, which guessed `{codigo, nome}`).
 * `tipo_documento` IS the code (also the multipart form field's value on
 * upload); there is no separate display label, only `descricao`. The
 * upload SIZE LIMIT is NOT exposed here (confirmed against the live
 * route) — never hardcode a client-side ceiling; show the server's typed
 * 400 verbatim when an upload is rejected instead.
 */
export interface TipoDocumento {
  tipo_documento: string;
  categoria_lgpd: string;
  descricao: string | null;
  /** RG/CPF-class — the types a tipo picker must group so an operator can
   *  actually find them, instead of scanning an alphabetical list for one
   *  of five names among a dozen. */
  identidade: boolean;
}

export type DocumentoAcao = "view" | "download" | "delete";

/**
 * ASSUMPTION — `cliente_documento_acessos` (§2) stores `usuario_id`, but
 * every other actor reference in this contract is served enriched
 * (`{id, nome}`); modelled consistently rather than forcing the FE to
 * resolve ids the API never gives it a list to resolve against.
 */
export interface Acesso {
  id: string;
  usuario: AtorRef | null;
  acao: DocumentoAcao;
  created_at: string;
}

export interface DocumentoUrlResponse {
  url: string;
  expires_at: string;
}

// ─── Card badges (screenshot 11 — the board face) ──────────────────────────

export interface Temperatura {
  valor: number;
  rotulo: string;
  /** D8 deferred the formula, not the component — always `true` this phase. */
  provisoria: true;
}

export interface CardBadges {
  notas: number;
  documentos: number;
  touches: number;
  checklist_total: number;
  checklist_concluidos: number;
  tem_descricao: boolean;
  temperatura: Temperatura | null;
}

// ─── Card summary (the badge row source) ───────────────────────────────────

/**
 * `GET {entity}/{id}/card` — the entity-agnostic part of the card summary.
 * A product's own summary type extends this with its entity record and any
 * relations only it has (SW: `cliente`, `atendimentos`), e.g.
 * `interface CardResumo extends CardResumoBase { cliente: Cliente; ... }`.
 */
export interface CardResumoBase {
  tags: Tag[];
  membros: Membro[];
  /**
   * The card's single Descrição is card STATE, served here — NEVER in the
   * timeline. `null` when no description exists yet.
   */
  descricao: Descricao | null;
  datas: CardDatas;
  badges: CardBadges;
}

// ─── Timeline (one thread, cursor-paginated) ───────────────────────────────

/**
 * The kinds the SEED gatherers produce (`noctusai_lib.domain.card_hub.timeline`
 * ships `nota`, `documento`, `checklist`), plus the two generic kinds a
 * product commonly registers (`movimento` — a pipeline stage move; `sistema`).
 * Products add their own kinds (SW: `touch`, `visita`) — the timeline renders
 * any kind via its renderer registry, and an unregistered kind through the
 * unknown-kind fallback. The union stays OPEN (`string & {}`) on purpose.
 */
export type TimelineKind =
  | "nota"
  | "documento"
  | "checklist"
  | "movimento"
  | "sistema"
  | (string & {});

export interface TimelineEntryBase {
  id: string;
  ocorrido_em: string;
  ator: AtorRef | null;
}

/**
 * Only `tipo='comentario'` notes ever appear here — the card's
 * `tipo='descricao'` note is card state (`CardResumoBase.descricao`), never a
 * timeline event.
 */
export interface TimelineNotaEntry extends TimelineEntryBase {
  kind: "nota";
  corpo: string;
  autor: AtorRef | null;
  editado_em: string | null;
  deleted_at: string | null;
}

export interface TimelineMovimentoEntry extends TimelineEntryBase {
  kind: "movimento";
  de_etapa: string | null;
  para_etapa: string;
}

export interface TimelineDocumentoEntry extends TimelineEntryBase {
  kind: "documento";
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
}

export interface TimelineChecklistEntry extends TimelineEntryBase {
  kind: "checklist";
  checklist_id: string;
  titulo: string;
  item_texto: string;
  concluido: boolean;
}

export interface TimelineSistemaEntry extends TimelineEntryBase {
  kind: "sistema";
  evento: string;
  detalhe: string | null;
}

/**
 * Forward-compat slot — an entry whose `kind` has no registered renderer must
 * still render, never crash and never be silently dropped. `[key: string]:
 * unknown` keeps whatever payload fields arrive without the FE needing to
 * know their shape.
 */
export interface TimelineUnknownEntry extends TimelineEntryBase {
  kind: string;
  [key: string]: unknown;
}

export type TimelineEntry =
  | TimelineNotaEntry
  | TimelineMovimentoEntry
  | TimelineDocumentoEntry
  | TimelineChecklistEntry
  | TimelineSistemaEntry
  | TimelineUnknownEntry;

export interface TimelinePage {
  items: TimelineEntry[];
  total: number;
  next_cursor: string | null;
}

// ─── Envelope helpers ───────────────────────────────────────────────────────

export interface ItemsEnvelope<T> {
  items: T[];
  total: number;
}

// ─── Checklist extras (operator-created rows) ──────────────────────────────

/**
 * A stored file, as the checklist surfaces reference it.
 *
 * Deliberately NARROWER than `Documento`: neither the mandatory checklist rows
 * nor the extras rows carry an LGPD category, a retention date or an uploader
 * — that belongs to the Anexos list, which is where a document is managed as a
 * document. Here a file is an ATTRIBUTE of a checklist row, and modelling it
 * with the full shape would invite a row to start rendering fields it has no
 * business owning.
 */
export interface ChecklistDocumentoRef {
  id: string;
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
  created_at: string;
}

/** Text data or file data — the two kinds of row the operator can create. */
export type ChecklistExtraTipo = "texto" | "arquivo";

/**
 * An operator-created checklist row (`GET /api/clientes/{id}/checklist-extras`).
 *
 * The list BESIDE the mandatory one, and its opposite in every way that
 * matters: these rows are created, renamed and destroyed by the person using
 * the card, because they hold whatever THIS deal needs that the fleet-wide
 * six do not.
 *
 * 🔴 `concluido` IS DERIVED, and there is no write path for it. The PATCH
 * contract accepts `label`, `valor_texto` and `ordem` only — a tick follows
 * from the row having a value or a file, exactly as the mandatory list's ticks
 * follow from the record. The UI therefore renders this checkbox as a readout,
 * never as a control; offering a checkbox that silently fails to persist would
 * be the lying-state failure one layer down.
 */
export interface ChecklistExtra {
  id: string;
  label: string;
  tipo: ChecklistExtraTipo;
  valor_texto: string | null;
  documento: ChecklistDocumentoRef | null;
  concluido: boolean;
  ordem: number;
}

export interface ChecklistExtrasResponse {
  items: ChecklistExtra[];
}

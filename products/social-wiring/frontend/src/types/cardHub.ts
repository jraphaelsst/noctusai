/**
 * The lead-card-hub Phase 2 "card" contract types —
 * `products/social-wiring/projects/lead-card-hub-p2-PROJECT.md` §3, built
 * against the API contract, NOT against observed behaviour (the backend is
 * being built in a PARALLEL worktree against the same document and does not
 * exist on this branch yet). Every shape below traces to a §3 table/route;
 * where §3 names a field without pinning its exact shape, the assumption is
 * called out inline (mirrors `useClientes.ts`'s convention for
 * `touch_count`/`atendimentos_abertos`).
 *
 * `components/card/**` (S3, ruling in §0) is presentational-only and may
 * import these types freely — they carry no fetching logic.
 */
import type { Cliente } from "@/hooks/useClientes";
import type { AtendimentoCampanha, AtendimentoLead } from "@/types/pipeline";

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

/**
 * `GET /clientes/{id}/card` — §3. `cliente` reuses the P1 `Cliente` shape
 * (§3: "existing GET /clientes/{id} shape"); `atendimentos` is D17's
 * active-plus-closed history and is intentionally untyped here — no shape
 * for it appears anywhere in this contract or in `types/pipeline.ts`, and
 * inventing one would be building past the contract (§5 anti-goal).
 */
export interface CardResumo {
  cliente: Cliente;
  tags: Tag[];
  membros: Membro[];
  /**
   * Backend correction, landed on `origin/dev`: the card's single
   * Descrição is card STATE, served here — NEVER in the timeline (see
   * `TimelineNotaEntry`'s docblock). `null` when no description exists yet.
   */
  descricao: Descricao | null;
  datas: CardDatas;
  badges: CardBadges;
  /**
   * D17's active-plus-closed history, each row carrying its ORIGIN record.
   *
   * Typed as of 2026-08-19, when the card started rendering the lead's own
   * data. It was `unknown[]` before, with a docblock saying inventing a shape
   * would be building past the contract — correct then, obsolete now: the
   * shape is no longer invented, it is `CARD_ORIGIN_SELECT`'s, and the same
   * `AtendimentoLead` / `AtendimentoCampanha` types the boards already use.
   *
   * `clientes` holds identity + card state and NO contact fields, so this is
   * the only place the card can learn a lead's phone, email or form answers.
   */
  atendimentos: CardAtendimento[];
}

/** One atendimento on the card, with the origin record embedded. */
export interface CardAtendimento {
  id: string;
  titulo: string | null;
  status: string | null;
  closed_at: string | null;
  created_at: string | null;
  lead_id: string | null;
  meta_ads_lead_id: string | null;
  /** Present when the card was spawned from a `social_wiring.leads` row. */
  lead: AtendimentoLead | null;
  /** Present when it was spawned from a `meta_ads_leads` row. Never both. */
  campanha: AtendimentoCampanha | null;
}

// ─── Agendamentos (migration 061 — many per atendimento) ──────────────────

export type TipoAgendamento = "visita" | "ligacao" | "reuniao" | "outro";

/**
 * One appointment. Belongs to an ATENDIMENTO, not to the person — D17 keeps
 * closed deals as history, so a visit booked for a 2024 purchase and one
 * booked for a live negotiation must not share a list. The card is the person
 * and reads across all of their atendimentos; each row still knows its deal.
 *
 * Replaces the single `CardDatas` slot, which physically could not hold two
 * ("it doesnt add multiple schedules, it replaces the last one").
 */
export interface Agendamento {
  id: string;
  atendimento_id: string;
  quando: string;
  tipo: TipoAgendamento;
  nota: string | null;
  /** `null` = no reminder wanted. `0` = at the time. Not the same thing. */
  lembrete_minutos_antes: number | null;
  created_at: string | null;
}

export interface AgendamentoCreateBody {
  quando: string;
  tipo: TipoAgendamento;
  nota?: string | null;
  lembrete_minutos_antes?: number | null;
  /** Only needed when the person has more than one open atendimento. */
  atendimento_id?: string;
}

export type AgendamentoPatchBody = Partial<Omit<AgendamentoCreateBody, "atendimento_id">>;

// ─── Timeline (D9 — one thread) ────────────────────────────────────────────

export type TimelineKind =
  | "nota"
  | "touch"
  | "movimento"
  | "documento"
  | "checklist"
  | "sistema";

interface TimelineEntryBase {
  id: string;
  ocorrido_em: string;
  ator: AtorRef | null;
}

/**
 * Only `tipo='comentario'` notes ever appear here — `card_hub/
 * timeline_service.py::_gather_notas` filters `tipo='comentario'`
 * explicitly. The card's `tipo='descricao'` note is card state
 * (`CardResumo.descricao`), never a timeline event.
 */
export interface TimelineNotaEntry extends TimelineEntryBase {
  kind: "nota";
  corpo: string;
  autor: AtorRef | null;
  editado_em: string | null;
  deleted_at: string | null;
}

export interface TimelineTouchEntry extends TimelineEntryBase {
  kind: "touch";
  origem_tabela: string;
  origem_id: string;
  origem_rotulo: string;
  resumo: string;
  dados: Record<string, unknown>;
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
 * Forward-compat slot for Phase 2b (WhatsApp/DM embed+reply) and anything
 * else — an entry whose `kind` this build does not recognise must still
 * render, never crash and never be silently dropped (§4). `[key: string]:
 * unknown` keeps whatever payload fields arrive without the FE needing to
 * know their shape.
 */
export interface TimelineUnknownEntry extends TimelineEntryBase {
  kind: string;
  [key: string]: unknown;
}

export type TimelineEntry =
  | TimelineNotaEntry
  | TimelineTouchEntry
  | TimelineMovimentoEntry
  | TimelineDocumentoEntry
  | TimelineChecklistEntry
  | TimelineSistemaEntry
  | TimelineUnknownEntry;

export const KNOWN_TIMELINE_KINDS: readonly TimelineKind[] = [
  "nota",
  "touch",
  "movimento",
  "documento",
  "checklist",
  "sistema",
];

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

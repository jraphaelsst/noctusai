/**
 * The lead-card-hub Phase 2 "card" contract types —
 * `products/social-wiring/projects/lead-card-hub-p2-PROJECT.md` §3, built
 * against the API contract, NOT against observed behaviour (the backend is
 * being built in a PARALLEL worktree against the same document and does not
 * exist on this branch yet). Every shape below traces to a §3 table/route;
 * where §3 names a field without pinning its exact shape, the assumption is
 * called out inline (mirrors `useClientes.ts`'s convention for
 * `touch_count`/`negociacoes_abertas`).
 *
 * `components/card/**` (S3, ruling in §0) is presentational-only and may
 * import these types freely — they carry no fetching logic.
 */
import type { Cliente } from "@/hooks/useClientes";

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
}

// ─── Notas ───────────────────────────────────────────────────────────────

export interface Nota {
  id: string;
  corpo: string;
  autor: AtorRef;
  /** `null` ⇒ never edited. */
  editado_em: string | null;
  /** Soft-delete tombstone — a deleted note still occupies its timeline slot. */
  deleted_at: string | null;
  /**
   * ASSUMPTION — §3 pins the timeline payload's fields but not the bare
   * POST/PATCH response's. Renders as "agora" when absent (the note was
   * just created) rather than a lying past timestamp.
   */
  criado_em?: string;
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
 * ASSUMPTION — §3 lists the route (`GET /clientes/documentos/tipos`) but not
 * `TipoDocumento`'s fields. Modelled as a code+label pair (enough to drive a
 * `<Select>`), following the enrichment pattern (`{id,nome}`) every other
 * reference type in this contract uses.
 */
export interface TipoDocumento {
  codigo: string;
  nome: string;
  categoria_lgpd: string;
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
 * (§3: "existing GET /clientes/{id} shape"); `negociacoes` is D17's
 * active-plus-closed history and is intentionally untyped here — no shape
 * for it appears anywhere in this contract or in `types/pipeline.ts`, and
 * inventing one would be building past the contract (§5 anti-goal).
 */
export interface CardResumo {
  cliente: Cliente;
  tags: Tag[];
  membros: Membro[];
  datas: CardDatas;
  badges: CardBadges;
  negociacoes: unknown[];
}

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

export interface TimelineNotaEntry extends TimelineEntryBase {
  kind: "nota";
  corpo: string;
  autor: AtorRef;
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

/**
 * Funnel organ — types. ONE board + card for every product; what differs per product (face slots,
 * tabs, actions, hub link) is a `FunnelSchema` literal, never a fork.
 *
 * Wire shapes mirror the funnel backend slice (`feat/seed-funnel-organ-be`): prefix `P`,
 * `GET P/meta`, `GET P/board`, `POST P/cards/{id}/mover-etapa|perder|reabrir|arquivar|acoes/{codigo}`.
 */
import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import type { PipelineStage } from '../types';

export type FunnelStatus = 'aberto' | 'ganho' | 'perdido' | 'arquivado';

export interface FunnelBadge {
  label: string;
  variant?: string;
}

/** The card DTO every funnel returns. Product extras ride in `campos`. */
export interface FunnelCard {
  id: string;
  etapa_id: string;
  kanban_pos: string;
  status: FunnelStatus;
  titulo: string;
  subtitulo: string | null;
  valor: number;
  responsavel: { id: string; nome: string } | null;
  badges: FunnelBadge[];
  motivo_perda_codigo: string | null;
  motivo_perda: string | null;
  created_at: string;
  updated_at: string;
  hub_entity_id: string | null;
  campos: Record<string, unknown>;
}

export interface FunnelLostReason {
  codigo: string;
  label: string;
  /** "Outro": the free-text is required. */
  exige_texto: boolean;
}

export interface FunnelGate {
  codigo: string;
  inputs: unknown[];
  mensagem: string;
}

export interface FunnelMetaAction {
  codigo: string;
  label: string;
  /** Stage roles the action is offered in; empty = any. */
  papeis: string[];
}

export interface FunnelMeta {
  pipeline: string;
  papeis: string[];
  lost_reasons: FunnelLostReason[];
  gates: Record<string, FunnelGate>;
  acoes: FunnelMetaAction[];
  campos_editaveis: string[];
}

/** One missing requirement of a refused gate (409 `gate_refused`). */
export interface FunnelPendencia {
  codigo: string;
  label: string;
}

/** A parsed server refusal — the shape every UI surface renders. */
export interface FunnelRefusal {
  code: string | null;
  mensagem: string;
  gate: string | null;
  pendencias: FunnelPendencia[];
}

// ─── Face (the board card) ──────────────────────────────────────────────────

export interface FunnelFaceAction {
  /** Must match an entry of `schema.actions`. */
  code: string;
  label: string;
}

export interface FunnelFaceIconAction extends FunnelFaceAction {
  icon: LucideIcon;
}

export interface FunnelFaceContext {
  stage: PipelineStage | null;
}

/** Slots are field ACCESSORS. Every slot is optional; defaults read the card DTO. */
export interface FunnelFaceSlots<TCard extends FunnelCard> {
  title?: (card: TCard) => string;
  subtitle?: (card: TCard) => string | null | undefined;
  /** Initials or an image. Absent = no avatar. */
  avatar?: (card: TCard) => { label: string; src?: string | null } | null;
  chips?: (card: TCard) => FunnelBadge[];
  /** Already formatted. Default: `formatFunnelValue` (one-off + monthly). */
  value?: (card: TCard) => string | null;
  owner?: (card: TCard) => { nome: string } | null;
  due?: (card: TCard) => { data_entrega: string; concluida?: boolean } | null;
  score?: (card: TCard) => { label: string } | null;
  /** The primary stage-role button ("Aceitar proposta"). */
  roleAction?: (card: TCard, ctx: FunnelFaceContext) => FunnelFaceAction | null;
  /** A secondary icon button ("Gerar orçamento"). Always carries an accessible name (`label`). */
  iconAction?: (card: TCard, ctx: FunnelFaceContext) => FunnelFaceIconAction | null;
}

// ─── Detail (the card dialog) ───────────────────────────────────────────────

export interface FunnelFieldDef<TCard extends FunnelCard> {
  /** Key inside `card.campos` (or any DTO key when `read` is given). */
  key: string;
  label: string;
  type?: 'text' | 'textarea' | 'number' | 'money' | 'date';
  /** Custom read (default `card.campos[key]`). */
  read?: (card: TCard) => unknown;
  /** Display formatter; missing values always render "—", never 0. */
  format?: (value: unknown, card: TCard) => string;
}

export interface FunnelLinkedColumn {
  key: string;
  label: string;
  /** Format the cell. Default: the raw string, "—" when missing. */
  format?: (value: unknown, row: Record<string, unknown>) => string;
}

export interface FunnelSectionRenderCtx<TCard extends FunnelCard> {
  card: TCard;
  /** Switch tab from inside a section. */
  select: (tabId: string) => void;
  isSheet: boolean;
}

export type FunnelSection<TCard extends FunnelCard> =
  /** The seed card-hub spine (etiquetas, descrição, anexos, checklists). Rendered by `renderers.geral`. */
  | { kind: 'geral' }
  /** Read-only grid of fields. */
  | { kind: 'fields'; fields: FunnelFieldDef<TCard>[] }
  /** Same grid, editable — saves through `PATCH P/cards/{id}` (only server-declared `campos_editaveis`). */
  | { kind: 'form'; fields: FunnelFieldDef<TCard>[] }
  /** A plain list derived from the card itself. */
  | { kind: 'list'; items: (card: TCard) => { id: string; label: string; detail?: string }[]; empty?: string }
  /** Rows of another entity linked to this card, fetched from `endpoint(card)`. */
  | {
      kind: 'linked';
      endpoint: (card: TCard) => string;
      columns: FunnelLinkedColumn[];
      rowId?: (row: Record<string, unknown>) => string;
      onOpen?: (row: Record<string, unknown>, card: TCard) => void;
      empty?: string;
    }
  /** Product-wired kinds (need product services): rendered by `renderers.<kind>`. */
  | { kind: 'schedule' }
  | { kind: 'reminders' }
  | { kind: 'conversation' }
  /** Stage-move history (`GET P/cards/{id}/movimentos`) — or the card-hub timeline when linked. */
  | { kind: 'timeline' }
  | { kind: 'custom'; render: (ctx: FunnelSectionRenderCtx<TCard>) => ReactNode };

export interface FunnelTab<TCard extends FunnelCard> {
  id: string;
  label: string;
  icon: LucideIcon;
  order?: number;
  /** Hide the tab for cards it does not apply to. */
  when?: (card: TCard) => boolean;
  section: FunnelSection<TCard>;
}

export interface FunnelActionInput {
  name: string;
  label: string;
  type?: 'text' | 'textarea' | 'number' | 'date';
  required?: boolean;
}

export interface FunnelActionDef {
  /** `POST P/cards/{id}/acoes/{code}`. */
  code: string;
  label: string;
  icon?: LucideIcon;
  placement: 'header' | 'face';
  /** Ask first. The string is the question; `inputs` are collected in the same dialog. */
  confirm?: string;
  inputs?: FunnelActionInput[];
}

export interface FunnelSchema<TCard extends FunnelCard = FunnelCard> {
  /** Unique id of this funnel context (also the root of test ids). */
  id: string;
  /** Noun for copy: "negócio", "lead", "atendimento". */
  entityLabel: string;
  face?: FunnelFaceSlots<TCard>;
  tabs: FunnelTab<TCard>[];
  actions?: FunnelActionDef[];
  /** The card-hub entity this card opens (`null` = no hub). Default: `card.hub_entity_id`. */
  hubEntityId?: (card: TCard) => string | null;
  /** Tab open on mount. Default: first visible tab. */
  defaultTab?: string;
}

/** Renderers a product injects for the section kinds that need product services. */
export interface FunnelRenderers<TCard extends FunnelCard> {
  geral?: (ctx: FunnelSectionRenderCtx<TCard>) => ReactNode;
  schedule?: (ctx: FunnelSectionRenderCtx<TCard>) => ReactNode;
  reminders?: (ctx: FunnelSectionRenderCtx<TCard>) => ReactNode;
  conversation?: (ctx: FunnelSectionRenderCtx<TCard>) => ReactNode;
}

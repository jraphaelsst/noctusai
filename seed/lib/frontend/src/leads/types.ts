/** Shapes of the leads API (`/api/leads`) -- the frontend half of `noctusai_lib.domain.leads`. */

export interface Lead {
  id: string;
  org_id?: string;
  name: string;
  /** Canonical E.164 (`+5511994573387`) or null. Render with `formatPhone`. */
  phone: string | null;
  email: string | null;
  /** Slug from the product's configured origins. */
  origin: string;
  /** Slug from the product's configured stages. */
  stage: string;
  position?: number;
  stage_changed_at?: string;
  notes: string | null;
  tags: string[];
  whatsapp_connection_id: string | null;
  whatsapp_chat_id: string | null;
  first_contact_at: string;
  last_message_at: string | null;
  last_message_preview: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface LeadStageConfig {
  slug: string;
  label: string;
  color: string | null;
}

export interface LeadOriginConfig {
  slug: string;
  label: string;
}

/** `GET /api/leads/config` -- stages and origins are DATA the product supplies. */
export interface LeadsConfigData {
  stages: LeadStageConfig[];
  origins: LeadOriginConfig[];
  whatsapp_origin: string;
  default_origin: string;
}

/** One kanban column of `GET /api/leads/board` (`etapa` = the stage slug; the shape the board cache ops expect). */
export interface LeadColumn {
  etapa: string;
  stage: LeadStageConfig;
  /** Every lead in the stage (matching the filters), even when `cards` is capped. */
  total: number;
  exibidos: number;
  cards: Lead[];
}

export interface LeadFiltersState {
  q?: string;
  origin?: string;
  /** `YYYY-MM-DD`, inclusive. */
  from?: string;
  to?: string;
  /** List only (the board has one column per stage). */
  stage?: string;
}

export interface LeadsPage {
  data: Lead[];
  next_cursor: string | null;
}

export interface LeadInput {
  name: string;
  phone?: string | null;
  email?: string | null;
  origin?: string | null;
  stage?: string | null;
  notes?: string | null;
  tags?: string[];
  /** ISO instant. */
  first_contact_at?: string | null;
}

export type LeadPatch = Partial<LeadInput>;

export interface LeadsEnvelope<T> {
  data: T;
}

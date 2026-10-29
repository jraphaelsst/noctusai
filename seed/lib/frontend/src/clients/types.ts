/**
 * Shapes of the clients API (`/api/clients`) -- the frontend half of `noctusai_lib.domain.clients`.
 * Recurring-session clients (patients, students, trainees): sessions, weekly slots, tags and their receivables.
 * Wire contract: money is integer CENTS, dates `YYYY-MM-DD`, instants ISO-8601 with offset, weekday 0 = Monday.
 */

/** A coloured option of the product's config (`color` = a pipeline `STAGE_COLORS` token). */
export interface ClientStatusConfig {
  slug: string;
  label: string;
  color: string | null;
}

export interface SessionStatusConfig extends ClientStatusConfig {
  /** A session in this status is charged (booked as a receivable). */
  billable: boolean;
}

export interface PaymentMethodConfig {
  slug: string;
  label: string;
}

/** `GET /api/clients/config` -- vocabulary, statuses and methods are DATA the product supplies. */
export interface ClientsConfigData {
  noun_singular: string;
  noun_plural: string;
  statuses: ClientStatusConfig[];
  session_statuses: SessionStatusConfig[];
  default_session_status: string;
  default_duration_min: number;
  default_price_cents: number | null;
  payment_methods: PaymentMethodConfig[];
  /** IANA zone every date / time of the organ is shown and typed in. */
  timezone: string;
  finance_enabled: boolean;
}

export interface ClientSummary {
  next_session_at: string | null;
  last_session_at: string | null;
  sessions_done: number;
  open_cents: number;
  overdue_cents: number;
  paid_cents: number;
}

export interface Client {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  /** CPF digits (masked for non-admins by the server). */
  doc: string | null;
  birth_date: string | null;
  status: string;
  tags: string[];
  notes: string | null;
  lead_id: string | null;
  whatsapp_chat_id: string | null;
  default_price_cents: number | null;
  session_duration_min: number | null;
  started_at: string;
  created_at: string;
  updated_at: string;
  summary: ClientSummary;
}

export type PaymentStatus = 'none' | 'open' | 'partial' | 'paid' | 'overdue';

export interface Session {
  id: string;
  client_id: string;
  client_name: string;
  schedule_id: string | null;
  starts_at: string;
  duration_min: number;
  status: string;
  /** null => the client's default price at booking time; still null => not charged. */
  price_cents: number | null;
  waive_charge: boolean;
  notes: string | null;
  entry_id: string | null;
  payment_status: PaymentStatus;
  created_at: string;
  updated_at: string;
}

export interface Schedule {
  id: string;
  client_id: string;
  /** 0 = Monday ... 6 = Sunday. */
  weekday: number;
  /** `HH:MM`. */
  time: string;
  duration_min: number;
  price_cents: number | null;
  starts_on: string;
  ends_on: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClientFinanceEntry {
  entry_id: string;
  session_id: string | null;
  description: string;
  amount_cents: number;
  settled_cents: number;
  due_date: string;
  status: string;
  overdue: boolean;
}

export interface ClientFinance {
  open_cents: number;
  overdue_cents: number;
  paid_cents: number;
  /** Newest first. */
  entries: ClientFinanceEntry[];
}

export interface ClientFiltersState {
  /** Name / phone / e-mail. */
  q?: string;
  status?: string;
  tag?: string;
}

export interface ClientsPage {
  data: Client[];
  next_cursor: string | null;
}

export interface ClientInput {
  name: string;
  phone?: string | null;
  email?: string | null;
  doc?: string | null;
  birth_date?: string | null;
  status?: string;
  tags?: string[];
  notes?: string | null;
  default_price_cents?: number | null;
  session_duration_min?: number | null;
  started_at?: string;
}
export type ClientPatch = Partial<ClientInput>;

export interface SessionInput {
  starts_at: string;
  duration_min?: number;
  status?: string;
  price_cents?: number | null;
  waive_charge?: boolean;
  notes?: string | null;
}
export type SessionPatch = Partial<SessionInput>;

export interface ScheduleInput {
  weekday: number;
  time: string;
  duration_min?: number;
  price_cents?: number | null;
  starts_on?: string;
  ends_on?: string | null;
}
export type SchedulePatch = Partial<ScheduleInput> & { active?: boolean };

export interface PaymentInput {
  amount_cents: number;
  paid_on: string;
  account_id: string;
  method: string;
  entry_ids?: string[];
  notes?: string | null;
}

export interface PaymentResult {
  settlement_ids: string[];
  finance: ClientFinance;
}

/** `GET /{id}/sessions` range + status filter (all optional). */
export interface SessionRange {
  from?: string;
  to?: string;
  status?: string;
}

export interface ClientsEnvelope<T> {
  data: T;
}

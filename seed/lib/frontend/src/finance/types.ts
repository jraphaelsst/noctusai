/**
 * Finance organ — wire types. Mirrors `noctusai_lib.domain.finance`
 * (`types.py`, `schemas.py`, `router.py`; `projects/commerce-seed-p4/CONTRACT.md §3`).
 * Money is integer CENTS everywhere. Names carry a `Finance` prefix where the
 * commerce organ already owns the bare name (`Category`, `Paginated`...), because
 * both organs are re-exported from the same `@noctusai/lib` barrel.
 *
 * The DRE/Simples/checklist shapes live in `dreTypes.ts` (CONTRACT §10.5, still
 * being implemented by the backend).
 */
import type { DreLine } from './dreTypes';

// ---------------------------------------------------------------------------
// Enums — const arrays + unions (exact backend values; a parity test pins them)
// ---------------------------------------------------------------------------

export const ACCOUNT_KINDS = ['checking', 'savings', 'cash', 'gateway', 'credit_card', 'investment'] as const;
export type AccountKind = (typeof ACCOUNT_KINDS)[number];

export const ENTRY_DIRECTIONS = ['payable', 'receivable'] as const;
export type EntryDirection = (typeof ENTRY_DIRECTIONS)[number];

export const ENTRY_STATUSES = ['open', 'partial', 'paid', 'cancelled'] as const;
export type EntryStatus = (typeof ENTRY_STATUSES)[number];

export const CATEGORY_DIRECTIONS = ['income', 'expense', 'transfer'] as const;
export type CategoryDirection = (typeof CATEGORY_DIRECTIONS)[number];

export const FREQUENCIES = [
  'daily',
  'weekly',
  'biweekly',
  'monthly',
  'bimonthly',
  'quarterly',
  'semiannual',
  'annual',
] as const;
export type Frequency = (typeof FREQUENCIES)[number];

export const ENTRY_SOURCES = ['manual', 'recurrence', 'installment', 'commerce_order', 'contracts', 'import', 'external', 'purchasing'] as const;
export type EntrySource = (typeof ENTRY_SOURCES)[number];

export const SETTLEMENT_KINDS = ['payment', 'refund'] as const;
export type SettlementKind = (typeof SETTLEMENT_KINDS)[number];

export const LEDGER_ORIGINS = ['settlement', 'fee', 'transfer', 'adjustment', 'opening'] as const;
export type LedgerOrigin = (typeof LEDGER_ORIGINS)[number];

export const STATEMENT_FORMATS = ['ofx', 'csv'] as const;
export type StatementFormat = (typeof STATEMENT_FORMATS)[number];

export const MATCH_STATUSES = ['unmatched', 'suggested', 'matched', 'ignored'] as const;
export type MatchStatus = (typeof MATCH_STATUSES)[number];

/** DRE behaviour of a category (CONTRACT §10.5 item 6). */
export const CATEGORY_BEHAVIORS = ['variable', 'fixed'] as const;
export type CategoryBehavior = (typeof CATEGORY_BEHAVIORS)[number];

/** MEI Relatório Mensal activity groups (E21); mirrors the backend `ActivityKind`. */
export const ACTIVITY_KINDS = ['comercio', 'industria', 'servicos'] as const;
export type ActivityKind = (typeof ACTIVITY_KINDS)[number];

// ---------------------------------------------------------------------------
// Envelopes
// ---------------------------------------------------------------------------

export interface FinanceEnvelope<T> {
  data: T;
}
export interface FinancePagination {
  page: number;
  page_size: number;
  total: number;
  total_pages?: number;
}
export interface FinancePaginated<T> {
  data: T[];
  pagination: FinancePagination;
}

// ---------------------------------------------------------------------------
// DTOs (rows as returned by the API)
// ---------------------------------------------------------------------------

export interface FinanceAccount {
  id: string;
  name: string;
  kind: AccountKind;
  bank_code: string | null;
  agency: string | null;
  number: string | null;
  opening_balance_cents: number;
  opening_date: string | null;
  gateway: string | null;
  active: boolean;
  /** The contador's reduced account code for this account (Domínio export); null = not set. */
  accounting_code?: string | null;
}

export interface AccountBalance {
  account_id: string;
  on: string;
  opening_balance_cents: number;
  movement_cents: number;
  balance_cents: number;
}

export interface FinanceCategory {
  id: string;
  parent_id: string | null;
  name: string;
  direction: CategoryDirection;
  is_default: boolean;
  active: boolean;
  /** DRE line this category rolls into (CONTRACT §10.3). `null` = unclassified. */
  dre_line?: DreLine | null;
  /** Variable/fixed — drives the managerial (contribution-margin) view. */
  behavior?: CategoryBehavior | null;
  /** The DAS tax category (routed by tax regime, CONTRACT §10.5.2). */
  is_das?: boolean;
  /** The contador's reduced account code for this category (Domínio export); null = not set. */
  accounting_code?: string | null;
  /** MEI Relatório Mensal group (comércio / indústria / serviços); inherited from the parent when null. */
  activity_kind?: ActivityKind | null;
}

export interface CostCenter {
  id: string;
  code: string;
  name: string;
  active: boolean;
}

export interface FinanceEntry {
  id: string;
  direction: EntryDirection;
  status: EntryStatus;
  /** Computed on read — never stored. */
  overdue: boolean;
  description: string;
  counterparty_name: string | null;
  /** Masked by the server for non-admins. */
  counterparty_doc: string | null;
  category_id: string | null;
  cost_center_id: string | null;
  expected_account_id: string | null;
  /** Link to the parties organ (null when not linked / not mounted); `counterparty_*` stays the snapshot. */
  party_id?: string | null;
  competence_month: string;
  due_date: string;
  amount_cents: number;
  settled_cents: number;
  source: EntrySource;
  source_ref: string | null;
  recurrence_id?: string | null;
  installment_group_id?: string | null;
  installment_n?: number | null;
  installment_total?: number | null;
  notes: string | null;
  /** Did the sale carry a nota fiscal? Feeds the MEI monthly report; null = not informed. */
  has_invoice?: boolean | null;
}

export interface Settlement {
  id: string;
  entry_id: string;
  account_id: string;
  kind: SettlementKind;
  settled_on: string;
  amount_cents: number;
  fee_cents: number;
  method: string | null;
  external_ref: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
}

export interface FinanceAttachment {
  id: string;
  entry_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  at: string;
  /** Short-lived signed URL (server-side TTL). */
  url: string;
  expires_in_seconds: number;
  disposition: string;
}

export interface FinanceEntryDetail extends FinanceEntry {
  settlements: Settlement[];
  attachments: Omit<FinanceAttachment, 'url' | 'expires_in_seconds' | 'disposition'>[];
  /** Server-computed: no settlement ever (reversed included) and a hand-booked source. Only then may it be deleted. */
  deletable?: boolean;
}

export interface RecurrenceTemplate {
  direction: EntryDirection;
  description: string;
  counterparty_name?: string | null;
  counterparty_doc?: string | null;
  category_id?: string | null;
  cost_center_id?: string | null;
  expected_account_id?: string | null;
  amount_cents: number;
  notes?: string | null;
}

export interface Recurrence {
  id: string;
  template: RecurrenceTemplate;
  frequency: Frequency;
  next_date: string;
  end_date: string | null;
  active: boolean;
}

export interface TransferResult {
  transfer_group: string;
  occurred_on: string;
  amount_cents: number;
  from_account_id: string;
  to_account_id: string;
  description: string;
}

export interface SettleResult {
  settlement: Settlement;
  entry: FinanceEntry;
  replayed: boolean;
}

// ---------------------------------------------------------------------------
// Request bodies
// ---------------------------------------------------------------------------

export interface AccountInput {
  name: string;
  kind: AccountKind;
  bank_code?: string | null;
  agency?: string | null;
  number?: string | null;
  opening_balance_cents?: number;
  opening_date?: string | null;
  gateway?: string | null;
  accounting_code?: string | null;
}
export type AccountPatch = Partial<Omit<AccountInput, 'kind'>> & { active?: boolean };

export interface FinanceCategoryInput {
  name: string;
  direction: CategoryDirection;
  parent_id?: string | null;
  dre_line?: DreLine | null;
  behavior?: CategoryBehavior | null;
  is_das?: boolean;
  accounting_code?: string | null;
  activity_kind?: ActivityKind | null;
}
export type FinanceCategoryPatch = Partial<Omit<FinanceCategoryInput, 'direction'>> & { active?: boolean };

export interface CostCenterInput {
  code: string;
  name: string;
}
export type CostCenterPatch = Partial<CostCenterInput> & { active?: boolean };

export interface EntryInput {
  direction: EntryDirection;
  description: string;
  counterparty_name?: string | null;
  counterparty_doc?: string | null;
  category_id?: string | null;
  cost_center_id?: string | null;
  expected_account_id?: string | null;
  party_id?: string | null;
  competence_month?: string | null;
  due_date: string;
  amount_cents: number;
  installments?: number;
  notes?: string | null;
  has_invoice?: boolean | null;
}
export type EntryPatch = Partial<Omit<EntryInput, 'direction' | 'installments'>>;

export interface SettleInput {
  account_id: string;
  kind?: SettlementKind;
  settled_on?: string | null;
  amount_cents: number;
  fee_cents?: number;
  method?: string | null;
  external_ref?: string | null;
}

export interface RecurrenceInput {
  template: RecurrenceTemplate;
  frequency: Frequency;
  next_date: string;
  end_date?: string | null;
  active?: boolean;
}
export interface RecurrencePatchInput {
  template?: Partial<RecurrenceTemplate>;
  frequency?: Frequency;
  next_date?: string;
  end_date?: string | null;
  active?: boolean;
}

export interface TransferInput {
  from_account_id: string;
  to_account_id: string;
  amount_cents: number;
  occurred_on?: string | null;
  description?: string | null;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface CashflowBucket {
  month: string;
  realized_in_cents: number;
  realized_out_cents: number;
  projected_in_cents: number;
  projected_out_cents: number;
}
export interface CashflowReportData {
  from: string;
  to: string;
  account_id: string | null;
  opening_balance_cents: number;
  buckets: CashflowBucket[];
  totals: {
    realized_in_cents: number;
    realized_out_cents: number;
    projected_in_cents: number;
    projected_out_cents: number;
  };
  closing_realized_balance_cents: number;
  closing_projected_balance_cents: number;
}

export const AGING_BUCKET_KEYS = ['d1_30', 'd31_60', 'd61_90', 'd90_plus'] as const;
export type AgingBucketKey = (typeof AGING_BUCKET_KEYS)[number];
export interface AgingCounterparty {
  counterparty_name: string | null;
  counterparty_doc: string | null;
  buckets: Record<AgingBucketKey, number>;
  total_cents: number;
  entries: number;
  oldest_due_date: string;
}
export interface AgingReportData {
  as_of: string;
  counterparties: AgingCounterparty[];
  totals: { buckets: Record<AgingBucketKey, number>; total_cents: number };
}

// ---------------------------------------------------------------------------
// Reconciliation
// ---------------------------------------------------------------------------

export interface StatementImport {
  id: string;
  account_id: string;
  format: StatementFormat;
  filename: string;
  sha256: string;
  period_start: string | null;
  period_end: string | null;
  at: string;
}
export interface StatementLine {
  id: string;
  import_id: string;
  account_id: string;
  posted_on: string;
  amount_cents: number;
  description: string;
  fitid: string;
  match_status: MatchStatus;
  ledger_id: string | null;
  suggested_entry_id: string | null;
}
export interface StatementImportResult {
  import: StatementImport;
  lines: number;
  duplicates_skipped: number;
  skipped_zero: number;
  suggested: number;
}
export interface MatchResult {
  line: StatementLine;
  entry: FinanceEntry;
  ledger_id: string;
  settlement_id: string;
  created_settlement: boolean;
}
export interface GatewayReviewItem {
  id: string;
  kind: string;
  occurred_on: string;
  amount_cents: number;
  charge_id: string | null;
  description: string;
  reason: string;
}
export interface GatewaySyncResult {
  account_id: string;
  status: 'ok' | 'partial' | 'error';
  pages: number;
  fetched: number;
  booked_fees: number;
  booked_transfers: number;
  already_booked: number;
  review: GatewayReviewItem[];
  review_total: number;
  error: string | null;
}
/** CSV column mapping (`CsvColumnMap`): a column is a header NAME or a 0-based INDEX. */
export interface CsvColumnMap {
  date: string | number;
  description: string | number;
  amount?: string | number;
  debit?: string | number;
  credit?: string | number;
  date_format?: 'dmy' | 'ymd' | 'dmy-dash' | 'dmy2';
  delimiter?: ',' | ';' | 'tab';
  has_header?: boolean;
  decimal?: 'comma' | 'dot';
  skip_rows?: number;
}

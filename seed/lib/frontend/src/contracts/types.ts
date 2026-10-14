/**
 * Contracts wire types — mirror `noctusai_lib/domain/contracts` (types.py / schemas.py / contracts.py).
 * Money is integer CENTS; percentages are basis points (`450` = 4.5%). Renaming a member is a wire-contract
 * change; the Python parity tests pin the same values.
 */
export const CONTRACT_STATUSES = ['draft', 'active', 'suspended', 'terminated', 'expired'] as const;
export type ContractStatus = (typeof CONTRACT_STATUSES)[number];

export const CONTRACT_BILLING_MODELS = ['one_time', 'installments', 'recurring', 'retainer'] as const;
export type ContractBillingModel = (typeof CONTRACT_BILLING_MODELS)[number];

export const CONTRACT_FREQUENCIES = ['monthly', 'quarterly', 'yearly'] as const;
export type ContractFrequency = (typeof CONTRACT_FREQUENCIES)[number];

export const CONTRACT_READJUSTMENT_INDEXES = ['none', 'IPCA', 'IGPM', 'INPC', 'fixed'] as const;
export type ContractReadjustmentIndex = (typeof CONTRACT_READJUSTMENT_INDEXES)[number];

export const CONTRACT_VERSION_KINDS = ['initial', 'amendment', 'readjustment', 'renewal', 'suspension', 'resumption', 'termination'] as const;
export type ContractVersionKind = (typeof CONTRACT_VERSION_KINDS)[number];

export const CONTRACT_BILLING_KINDS = ['fixed', 'excess', 'penalty'] as const;
export type ContractBillingKind = (typeof CONTRACT_BILLING_KINDS)[number];

export const CONTRACT_SIGNATURE_STATUSES = ['none', 'pendente', 'parcial', 'concluido', 'cancelado', 'expirado'] as const;
export type ContractSignatureStatus = (typeof CONTRACT_SIGNATURE_STATUSES)[number];

/** Stable machine codes of the backend (`errors.py`). */
export const CONTRACTS_ERROR_CODES = [
  'contrato_finalizado', 'transicao_invalida', 'contrato_vigente_use_aditivo', 'contrato_nao_rascunho', 'parte_invalida',
  'item_invalido', 'numero_duplicado', 'modelo_cobranca_invalido', 'reajuste_nao_aplicavel', 'aviso_previo_nao_cumprido',
  'periodo_ja_faturado', 'uso_nao_aplicavel', 'assinatura_nao_configurada', 'assinatura_em_andamento', 'signatario_invalido',
  'documento_nao_gerado', 'armazenamento_nao_configurado', 'documento_invalido',
] as const;

export interface ContractLine {
  id?: string;
  item_id?: string | null;
  description: string;
  quantity: number;
  unit_price_cents: number;
}

export interface Contract {
  id: string;
  org_id: string;
  number: string | null;
  title: string;
  party_id: string | null;
  party_name: string | null;
  /** MASKED (`***.456.789-**`) for non-admin readers. */
  party_doc: string | null;
  status: ContractStatus;
  billing_model: ContractBillingModel;
  amount_cents: number;
  frequency: ContractFrequency | null;
  installments_count: number | null;
  due_day: number | null;
  first_due_date: string | null;
  next_period_on: string | null;
  start_date: string | null;
  end_date: string | null;
  auto_renew: boolean;
  renewal_months: number;
  retainer_minutes: number | null;
  excess_rate_cents: number | null;
  readjustment_index: ContractReadjustmentIndex;
  readjustment_percent_bp: number | null;
  readjustment_every_months: number;
  last_readjusted_on: string | null;
  notice_days: number;
  penalty_cents: number;
  penalty_bp: number;
  penalty_applied_cents: number | null;
  document_body: string | null;
  version_n: number;
  activated_at: string | null;
  suspended_at: string | null;
  suspension_reason: string | null;
  terminated_on: string | null;
  termination_reason: string | null;
  signature_status: ContractSignatureStatus;
  signed_at: string | null;
  source_quote_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  // computed by the server on read
  terminable_from: string;
  readjustment_due_on: string | null;
  lapsed: boolean;
  /** Only on the by-id read. */
  lines?: ContractLine[];
  /** Only right after `sendSignature`. */
  signature_link?: string | null;
}

export interface ContractVersion {
  id: string;
  contract_id: string;
  version_n: number;
  kind: ContractVersionKind;
  summary: string | null;
  changes: Record<string, { from: unknown; to: unknown }>;
  effective_on: string | null;
  created_at: string;
}

export interface ContractBillingItem {
  period_key: string;
  kind: ContractBillingKind;
  due_date: string;
  competence_month: string;
  amount_cents: number;
  description: string;
}

export interface ContractBillingPreviewData {
  items: ContractBillingItem[];
  billed: number;
  running_month?: { month: string; minutes: number; included_minutes: number | null; excess_cents: number };
}

export interface ContractBillingRecord {
  id: string;
  contract_id: string;
  period_key: string;
  kind: ContractBillingKind;
  entry_id: string | null;
  amount_cents: number;
  due_date: string;
}

export interface ContractUsageMonth {
  month: string;
  minutes: number;
  included_minutes: number | null;
  excess_cents: number;
}

export interface ContractReadjustResult {
  applied: boolean;
  index: ContractReadjustmentIndex;
  percent_bp: number;
  effective_on: string;
  amount_cents_before: number;
  amount_cents_after: number;
  excess_rate_cents_before: number | null;
  excess_rate_cents_after: number | null;
}

/** Body of `POST /api/contracts` (the editor builds it; `lines` XOR `amount_cents`). */
export interface ContractInput {
  title: string;
  billing_model: ContractBillingModel;
  number?: string | null;
  party_id?: string | null;
  party_name?: string | null;
  party_doc?: string | null;
  amount_cents?: number | null;
  lines?: ContractLine[];
  frequency?: ContractFrequency | null;
  installments_count?: number | null;
  due_day?: number | null;
  first_due_date?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  auto_renew?: boolean;
  renewal_months?: number;
  retainer_minutes?: number | null;
  excess_rate_cents?: number | null;
  readjustment_index?: ContractReadjustmentIndex;
  readjustment_percent_bp?: number | null;
  readjustment_every_months?: number;
  notice_days?: number;
  penalty_cents?: number;
  penalty_bp?: number;
  notes?: string | null;
}

export type ContractPatch = Partial<ContractInput>;

/** The terms an amendment may change on a vigente contract. */
export type ContractTermChanges = Partial<
  Pick<
    ContractInput,
    | 'amount_cents' | 'lines' | 'end_date' | 'due_day' | 'auto_renew' | 'renewal_months' | 'retainer_minutes' | 'excess_rate_cents'
    | 'readjustment_index' | 'readjustment_percent_bp' | 'readjustment_every_months' | 'notice_days' | 'penalty_cents' | 'penalty_bp'
  >
>;

export interface ContractTerminateInput {
  reason: string;
  effective_on?: string | null;
  waive_notice?: boolean;
  waive_penalty?: boolean;
}

export interface ContractsListParams {
  q?: string;
  status?: ContractStatus | '';
  billing_model?: ContractBillingModel | '';
  party_id?: string;
  expiring_within_days?: number;
  page?: number;
  page_size?: number;
}

export interface ContractsPaginated<T> {
  data: T[];
  pagination: { page: number; page_size: number; total: number; total_pages?: number };
}

export interface ContractsEnvelope<T> {
  data: T;
}

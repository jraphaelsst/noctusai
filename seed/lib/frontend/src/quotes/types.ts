/**
 * Quotes wire types — mirror `noctusai_lib/domain/quotes` (types.py / schemas.py / quotes.py / public.py).
 * Renaming a member here is a wire-contract change; the Python parity tests pin the same values.
 * Names are `Quote*`-prefixed on purpose: `commerce` already exports `Quote` / `QuoteLine` (the cart quote).
 */

export const QUOTE_STATUSES = ['draft', 'sent', 'viewed', 'accepted', 'rejected', 'expired', 'superseded'] as const;
export type QuoteStatus = (typeof QUOTE_STATUSES)[number];

export const QUOTE_LINE_KINDS = ['goods', 'service'] as const;
export type QuoteLineKind = (typeof QUOTE_LINE_KINDS)[number];

export const QUOTE_CONVERT_TO = ['order', 'contract', 'none'] as const;
export type QuoteConvertTo = (typeof QUOTE_CONVERT_TO)[number];

export const QUOTE_CONVERSION_STATUSES = ['none', 'pending', 'done', 'failed', 'skipped'] as const;
export type QuoteConversionStatus = (typeof QUOTE_CONVERSION_STATUSES)[number];

/** Stable machine codes of the backend (`errors.py`). */
export const QUOTE_ERROR_CODES = {
  orcamentoVazio: 'orcamento_vazio',
  orcamentoBloqueado: 'orcamento_bloqueado',
  orcamentoExpirado: 'orcamento_expirado',
  orcamentoEncerrado: 'orcamento_encerrado',
  orcamentoSubstituido: 'orcamento_substituido',
  transicaoInvalida: 'transicao_invalida',
  descontoInvalido: 'desconto_invalido',
  clienteInvalido: 'cliente_invalido',
  itemInvalido: 'item_invalido',
  linhaInvalida: 'linha_invalida',
  validadeInvalida: 'validade_invalida',
  consentimentoObrigatorio: 'consentimento_obrigatorio',
  nomeObrigatorio: 'nome_obrigatorio',
  motivoObrigatorio: 'motivo_obrigatorio',
  linkInvalido: 'link_invalido',
  linkIndisponivel: 'link_indisponivel',
  emailIndisponivel: 'email_indisponivel',
  envioFalhou: 'envio_falhou',
  conversaoIndisponivel: 'conversao_indisponivel',
} as const;

export interface QuoteLineRecord {
  id: string;
  position: number;
  item_id: string | null;
  description: string;
  unit: string;
  kind: QuoteLineKind;
  /** Decimal, up to 3 places. */
  qty: number;
  unit_price_cents: number;
  discount_cents: number;
  total_cents: number;
}

export interface QuotePartyRef {
  id: string;
  legal_name: string;
  trade_name: string | null;
  email: string | null;
}

export interface QuoteRecord {
  id: string;
  org_id: string;
  number: string;
  root_id: string;
  version: number;
  is_current: boolean;
  party_id: string;
  title: string | null;
  status: QuoteStatus;
  currency: string;
  valid_until: string | null;
  notes: string | null;
  terms: string | null;
  convert_to: QuoteConvertTo | null;
  subtotal_cents: number;
  discount_cents: number;
  total_cents: number;
  sent_at: string | null;
  last_sent_to: string | null;
  viewed_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
  expired_at: string | null;
  rejection_reason: string | null;
  conversion_status: QuoteConversionStatus;
  conversion_kind: string | null;
  conversion_ref: string | null;
  conversion_error: string | null;
  signature_ref: string | null;
  signature_status: string | null;
  created_at: string;
  updated_at: string;
  /** Present on the detail read (not on list rows). */
  lines?: QuoteLineRecord[];
  effective_convert_to?: QuoteConvertTo;
  party?: QuotePartyRef | null;
}

export interface QuoteLineInput {
  item_id?: string | null;
  description?: string;
  unit?: string;
  kind?: QuoteLineKind;
  /** Decimal string (`'2.5'`), never a float. */
  qty: string;
  unit_price_cents?: number;
  discount_cents?: number;
}

export interface QuoteInput {
  party_id: string;
  title?: string | null;
  valid_until?: string | null;
  notes?: string | null;
  terms?: string | null;
  discount_cents?: number;
  convert_to?: QuoteConvertTo | null;
  lines: QuoteLineInput[];
}
export type QuotePatch = Partial<QuoteInput>;

export interface QuoteCalculation {
  subtotal_cents: number;
  discount_cents: number;
  total_cents: number;
  lines: QuoteLineRecord[];
  effective_convert_to: QuoteConvertTo;
}

export interface QuoteSendInput {
  channel: 'email' | 'link';
  to?: string;
  message?: string;
}
export interface QuoteSendResult {
  quote: QuoteRecord;
  channel: 'email' | 'link';
  /** The public accept URL — a bearer credential, shown to staff only. */
  url: string;
  sent_to: string | null;
}

export interface QuoteAcceptance {
  id: string;
  quote_id: string;
  decision: 'accepted' | 'rejected';
  channel: 'public_link' | 'staff';
  signer_name: string;
  reason: string | null;
  consent_text: string | null;
  content_sha256: string;
  ip: string | null;
  decided_at: string;
}

export interface QuoteEventRecord {
  id: string;
  seq: number;
  kind: string;
  from_status: string | null;
  to_status: string | null;
  detail: Record<string, unknown>;
  at: string;
}

export interface QuotePagination {
  page: number;
  page_size: number;
  total: number;
  total_pages?: number;
}
export interface QuotePaginated<T> {
  data: T[];
  pagination: QuotePagination;
}
export interface QuoteEnvelope<T> {
  data: T;
}

export interface QuoteListParams {
  q?: string;
  status?: QuoteStatus | '';
  party_id?: string;
  include_versions?: boolean;
  page?: number;
  page_size?: number;
}

/** What the customer sees on the public link (allow-listed server-side: no document, e-mail, phones, internal ids). */
export interface QuotePublicView {
  number: string;
  version: number;
  title: string | null;
  status: QuoteStatus;
  currency: string;
  valid_until: string | null;
  notes: string | null;
  terms: string | null;
  subtotal_cents: number;
  discount_cents: number;
  total_cents: number;
  party_name: string;
  issuer_name: string;
  lines: Array<{
    position: number;
    description: string;
    unit: string;
    qty: number;
    unit_price_cents: number;
    discount_cents: number;
    total_cents: number;
  }>;
  can_decide: boolean;
  decision: { decision: 'accepted' | 'rejected'; decided_at: string } | null;
  /** Contains `{name}` — the page substitutes what the customer typed; the server stores the same sentence. */
  consent_template: string | null;
}

/** Option lists the host supplies (the parties / items organs own those names). */
export interface QuotePartyOption {
  id: string;
  name: string;
  email?: string | null;
}
export interface QuoteItemOption {
  id: string;
  name: string;
  unit?: string;
  price_cents?: number | null;
  kind?: QuoteLineKind;
}

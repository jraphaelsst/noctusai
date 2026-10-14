/**
 * Commerce organ — fiscal types (CONTRACT `projects/commerce-seed-p4/CONTRACT.md` §2.3–§2.5, slice B2).
 *
 * Enums mirror the backend `noctusai_lib.domain.commerce.fiscal_types` (which re-exports the
 * invoice organ's `InvoiceKind` / `InvoiceStatus` / `NfseMode`) EXACTLY; a backend parity test
 * (`test_fiscal_types_parity.py`) parses this file. Kept apart from `types.ts` (owned by the
 * money-states slice) so the two can land independently.
 */

export const INVOICE_KINDS = ['nfe', 'nfse'] as const;
export type InvoiceKind = (typeof INVOICE_KINDS)[number];

export const INVOICE_STATUSES = ['processing', 'authorized', 'rejected', 'cancelled', 'error'] as const;
export type InvoiceStatus = (typeof INVOICE_STATUSES)[number];

export const NFSE_MODES = ['nacional', 'municipal'] as const;
export type NfseMode = (typeof NFSE_MODES)[number];

export const CERTIFICATE_STATUSES = ['ausente', 'vencido', 'divergente', 'valido'] as const;
export type CertificateStatus = (typeof CERTIFICATE_STATUSES)[number];

/** Typed confirmation phrases the org admin must type (approved cutover, D19). */
export const NFSE_CUTOVER_PHRASE = 'MIGRAR PARA NFS-E NACIONAL';
export const NFSE_ROLLBACK_PHRASE = 'VOLTAR PARA NFS-E MUNICIPAL';

/** Certificate upload bounds (enforced server-side too). */
export const MAX_CERTIFICATE_BYTES = 64 * 1024;
export const MAX_CERTIFICATE_PASSWORD_CHARS = 128;

export interface NfseCutover {
  requested_at?: string;
  approved_at?: string;
  approved_by?: string | null;
  previous_mode?: NfseMode;
  validation_until?: string;
  rolled_back_at?: string;
  rolled_back_by?: string | null;
}

/** `GET /api/commerce/fiscal` — never carries provider tokens. */
export interface FiscalView {
  cnpj: string;
  tax_regime: string;
  inscricao_municipal: string | null;
  inscricao_estadual: string | null;
  municipio_ibge: string | null;
  invoice_company_ref: string | null;
  certificate_valid_until: string | null;
  certificate_cnpj: string | null;
  auto_issue_invoices: boolean;
  nfse_mode: NfseMode;
  nfse_cutover: NfseCutover;
  nfse_nacional_forced: boolean;
  certificate_status: CertificateStatus;
  can_cutover: boolean;
  can_rollback: boolean;
  version: number;
}

export interface FiscalUpdate {
  expected_version: number;
  inscricao_municipal?: string | null;
  inscricao_estadual?: string | null;
  municipio_ibge?: string | null;
  nfse_mode?: NfseMode;
  auto_issue_invoices?: boolean;
}

export interface InvoiceRejection {
  op: 'issue' | 'cancel';
  code: string | null;
  reasons: string[];
  at: string;
}

export interface Invoice {
  id: string;
  order_id: string;
  kind: InvoiceKind;
  seq: number;
  ref: string;
  status: InvoiceStatus;
  provider: string | null;
  number: string | null;
  series: string | null;
  access_key: string | null;
  verification_code: string | null;
  pdf_path: string | null;
  xml_path: string | null;
  rejection: InvoiceRejection | null;
  cancel_reason: string | null;
  cancel_requested_at: string | null;
  issued_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
}

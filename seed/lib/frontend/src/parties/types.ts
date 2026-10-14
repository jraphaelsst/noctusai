/**
 * Parties wire types — mirror `noctusai_lib/domain/parties` (types.py / schemas.py / parties.py).
 * Renaming a member here is a wire-contract change; the Python parity tests pin the same values.
 */

export const PARTY_KINDS = ['PF', 'PJ'] as const;
export type PartyKind = (typeof PARTY_KINDS)[number];

export const PARTY_ROLES = ['customer', 'supplier', 'employee', 'carrier'] as const;
export type PartyRole = (typeof PARTY_ROLES)[number];

export const ADDRESS_FIELDS = ['street', 'number', 'complement', 'district', 'city', 'state', 'zip', 'country'] as const;
export type AddressField = (typeof ADDRESS_FIELDS)[number];
export type PartyAddress = Partial<Record<AddressField, string>>;

/** Stable machine codes of the backend (`errors.py`). */
export const PARTIES_ERROR_CODES = {
  documentoInvalido: 'documento_invalido',
  documentoDuplicado: 'documento_duplicado',
  parceiroEmUso: 'parceiro_em_uso',
  emailInvalido: 'email_invalido',
  telefoneInvalido: 'telefone_invalido',
  papelInvalido: 'papel_invalido',
  importacaoInvalida: 'importacao_invalida',
  importacaoGrandeDemais: 'importacao_grande_demais',
  exportacaoGrandeDemais: 'exportacao_grande_demais',
} as const;

export interface Party {
  id: string;
  org_id: string;
  kind: PartyKind;
  /** Digits / alphanumeric, no punctuation. MASKED (`***.456.789-**`) for non-admin readers. */
  doc: string | null;
  legal_name: string;
  trade_name: string | null;
  email: string | null;
  /** E.164, e.g. `+5511994573387`. */
  phones: string[];
  address: PartyAddress;
  state_registration: string | null;
  municipal_registration: string | null;
  notes: string | null;
  is_active: boolean;
  roles: PartyRole[];
  created_at: string;
  updated_at: string;
}

/** Body of `POST /api/parties`. */
export interface PartyInput {
  kind: PartyKind;
  doc?: string | null;
  legal_name: string;
  trade_name?: string | null;
  email?: string | null;
  phones?: string[];
  address?: PartyAddress | null;
  state_registration?: string | null;
  municipal_registration?: string | null;
  notes?: string | null;
  roles?: PartyRole[];
}

/** Body of `PATCH /api/parties/{id}` — only the keys present are changed; `roles` REPLACES the set. */
export type PartyPatch = Partial<PartyInput>;

export interface PartiesPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages?: number;
}
export interface PartiesPaginated<T> {
  data: T[];
  pagination: PartiesPagination;
}
export interface PartiesEnvelope<T> {
  data: T;
}

export type PartiesActiveFilter = 'active' | 'archived' | 'all';

export interface PartiesListParams {
  q?: string;
  kind?: PartyKind | '';
  role?: PartyRole | '';
  active?: PartiesActiveFilter;
  page?: number;
  page_size?: number;
}

export interface PartiesImportRowIssue {
  line: number;
  field?: string | null;
  code?: string;
  message?: string;
  reason?: string;
}
export interface PartiesImportResult {
  dry_run: boolean;
  created: number;
  skipped: PartiesImportRowIssue[];
  errors: PartiesImportRowIssue[];
}

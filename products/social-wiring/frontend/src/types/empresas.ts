/**
 * Empresas — the P0c contract's company-due-diligence surface
 * (`project-history/roadmaps/sw-drive-extraction-P0c-contract.md` §D.1-4).
 *
 * Built against the CONTRACT, not against observed behaviour: S2a (the
 * backend) is being built in a PARALLEL worktree against the same document
 * and does not exist on this branch yet — same convention `types/cardHub.ts`
 * already documents for this product.
 *
 * `components/card/**` (presentational-only) and `hooks/useEmpresas.ts` both
 * import these types freely.
 */
import type { AtorRef, ItemsEnvelope } from "@/types/cardHub";
import type { LadoParte } from "@/types/cardHub";
import type { SituacaoCadastral } from "@/types/certidoesEstruturadas";

// ─── The empresa itself ─────────────────────────────────────────────────────

export interface EmpresaCard {
  id: string;
  cnpj: string;
  razao_social: string | null;
  nome_fantasia: string | null;
  natureza_juridica: string | null;
  data_abertura: string | null; // YYYY-MM-DD
  /** `null` until a Cartão CNPJ (or a backfilled certidão consulta) has
   *  supplied one — see the contract §A.1/§H4: a backfilled empresa is NOT
   *  given a situação, on purpose. */
  situacao_cadastral: SituacaoCadastral | null;
  /** "DATA DA SITUAÇÃO CADASTRAL" — the CLOSING date when baixada. The
   *  Cartão CNPJ is the only source of truth for this (§H4); a legacy
   *  Crednet-derived empresa carries `null` here even with a situação. */
  data_situacao_cadastral: string | null; // YYYY-MM-DD
  motivo_situacao: string | null;
  uf: string | null;
  /** Which channel first wrote this empresa's group-level fields
   *  (`'certidao_consulta' | 'serasa_crednet' | 'cartao_cnpj' | 'manual'`). */
  dados_origem: string | null;
  dados_confirmado_em: string | null;
}

// ─── Owners (§D.1 — one row per participação, spouses merged) ──────────────

export interface EmpresaOwner {
  cliente_id: string;
  nome: string;
  lado: LadoParte;
  papel: string;
  participacao_pct: number | null;
  /** `'serasa_crednet' | 'manual' | 'certidao_consulta'` — the
   *  `cliente_empresa_participacoes.origem` CHECK vocabulary (§A.2). */
  origem: string;
  /** Whether THIS owner is one of the people the contract requires
   *  certidões for — vendedor, their cônjuge, or a comprador (+cônjuge)
   *  when `tem_permuta`. `exige_certidoes` on the parent item is
   *  `E1 passes ∧ ≥1 owner certificando`. */
  certificando: boolean;
}

// ─── Cartão CNPJ slot summary (§D.1 — embedded in the list row) ───────────

export interface EmpresaCartaoResumo {
  documento_id: string | null;
  extracao_status: EmpresaDocumentoExtracaoStatus | null;
  extracao_descartada_em: string | null;
  /** e.g. `"cnpj_divergente"` — the vision-read CNPJ on the Cartão did not
   *  match the empresa's own CNPJ (§C.6, H10's accepted mitigation). */
  aviso: string | null;
}

// ─── The E1 classification (§E.1) ──────────────────────────────────────────

export type EmpresaMotivo =
  | "ativa"
  | "baixada_menos_5_anos"
  | "baixada_5_anos_ou_mais"
  | "sem_cartao_cnpj"
  | "outra_situacao"
  | "sem_socio_certificando";

/** `certidao_resultados.resultado`'s vocabulary PLUS the consulta-level
 *  `"pendente"` bucket the empresa summary's `por_resultado` map also
 *  counts (§D.1's example payload) — a resultado that has no `resultado`
 *  value yet is still counted, under this key, never dropped. */
export type EmpresaCertidaoResultadoBucket =
  | "negativa"
  | "positiva"
  | "positiva_com_efeito_de_negativa"
  | "negativa_com_homonimos"
  | "nao_emitida"
  | "pendente";

export interface EmpresaCertidoesResumo {
  consulta_ids: string[];
  total: number;
  por_resultado: Record<EmpresaCertidaoResultadoBucket, number>;
}

export interface EmpresaCardItem {
  empresa: EmpresaCard;
  owners: EmpresaOwner[];
  cartao: EmpresaCartaoResumo;
  exige_certidoes: boolean;
  motivo: EmpresaMotivo;
  certidoes: EmpresaCertidoesResumo;
}

/** `GET /api/clientes/{cliente_id}/empresas` (§D.1). Card route — a raw
 *  dict, not the `success_response()` envelope the certidões family uses. */
export interface EmpresasDoCardResponse {
  atendimento_id: string | null;
  referencia: string; // YYYY-MM-DD
  items: EmpresaCardItem[];
}

/** `POST /api/clientes/{cliente_id}/empresas` (§D.2) — manual link. */
export interface AdicionarEmpresaBody {
  cnpj: string;
  /** A participant on THIS card — titular, a party of either lado, or a
   *  vendedor's linked cônjuge. */
  cliente_id: string;
  razao_social?: string;
  participacao_pct?: number;
}

// ─── Empresa documentos (§A.3, §D.4 — the Cartão CNPJ engine) ─────────────

export type EmpresaDocumentoExtracaoStatus =
  | "pendente"
  | "processando"
  | "ok"
  | "sem_dados"
  | "erro";

/** `cartao_cnpj.py::CartaoCnpjFields` (§B) — the reading, kept as a loose
 *  record rather than mirroring every field: this UI reads only the
 *  handful the slot needs (`situacao_cadastral`, `data_situacao_cadastral`),
 *  and typing every per-field confiança/rótulo pair here would drift the
 *  moment the extractor's shape does. */
export type EmpresaDocumentoExtracaoDados = Record<string, unknown>;

export interface EmpresaDocumento {
  id: string;
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
  tipo_documento: "cartao_cnpj";
  enviado_por: AtorRef;
  created_at: string;
  extracao_status: EmpresaDocumentoExtracaoStatus | null;
  extracao_erro: string | null;
  extracao_dados: EmpresaDocumentoExtracaoDados | null;
  extracao_descartada_em: string | null;
}

export type EmpresaDocumentosResponse = ItemsEnvelope<EmpresaDocumento>;

// ─── Slice D — edit/delete/checklist ───────────────────────────────────────

/** `PATCH /api/empresas/{empresa_id}` — every field optional (only touched
 *  fields are sent). `cnpj` is never gated; the cadastral fields are gated
 *  as ONE group when the empresa's `dados_origem` is machine-sourced (see
 *  `dados_service.atualizar_manual`'s own docstring). */
export interface AtualizarEmpresaBody {
  cnpj?: string;
  razao_social?: string;
  nome_fantasia?: string;
  situacao_cadastral?: SituacaoCadastral;
  data_situacao_cadastral?: string;
}

/** The empresa row plus `pendente_confirmacao` — item keys this PATCH
 *  deferred to admin adjudication (empty when nothing was). */
export type AtualizarEmpresaResponse = EmpresaCard & {
  pendente_confirmacao: string[];
};

/** `DELETE /api/clientes/{cliente_id}/empresas/{empresa_id}` — unlinks
 *  always; `empresa_removida` only when this was the last participação.
 *  `storage_falhas` — bucket keys a storage removal did NOT confirm, never
 *  swallowed into a bare 200 (mirrors `ClienteDeleteOut`). */
export interface RemoverEmpresaResponse {
  participacao_removida: boolean;
  empresa_removida: boolean;
  documentos_removidos: number;
  storage_falhas: string[];
}

/** `GET /api/empresas/{empresa_id}/checklist` — today, ONE item
 *  (`cartao_cnpj`, always required). The PJ-vendedor-conditional items
 *  are NOT built (no PJ-vs-PF marker exists on `clientes`/`atendimento_
 *  partes` in this product — see `checklist_service.py`'s own docstring). */
export interface EmpresaChecklistItem {
  item_key: "cartao_cnpj";
  titulo: string;
  satisfeito: boolean;
  documento_id: string | null;
  obrigatorio: boolean;
}

export type EmpresaChecklistResponse = ItemsEnvelope<EmpresaChecklistItem>;

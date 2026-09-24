/**
 * Contratos — the deal's legal paperwork: uploaded today, auto-generated
 * later. Legal works in revisions, so each contract carries a STATUS and a
 * VERSION history rather than a single file.
 *
 * 🔴 A CONTRACT CAN ARRIVE WITHOUT A HUMAN UPLOAD. `origem: "gerado"` means
 * a later automation produced it — it lands in the SAME list, not a second
 * one, because from the corretor's chair "does this card have a contract"
 * has one answer regardless of who typed it. The UI marks it, never hides
 * or forks it.
 *
 * Shape mirrors `useFinanciamento.ts`: multipart bypasses the JSON-only seed
 * `api` client (raw `fetch` + the auth header pulled from supabase), JSON
 * mutations go through `api`.
 */
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@noctusai/lib";
import { api, supabase } from "@noctusai/seed/infra";

import { apiUrl } from "@/lib/apiBase";
import { formatBytes } from "@/hooks/useFinanciamento";

// ─── Types ──────────────────────────────────────────────────────────────────

export type ContratoStatus =
  | "rascunho"
  | "em_revisao"
  | "enviado_assinatura"
  | "assinado"
  | "cancelado";

export type ContratoModelo =
  | "compra_venda"
  | "compra_venda_permuta"
  | "compra_venda_a_vista"
  | "outro";

export type ContratoOrigem = "upload" | "gerado";

/**
 * Migration 157 — how the contract gets signed, and THE GATE between the two
 * flows: `digital` = the e-signature envelope ("Enviar para assinatura");
 * `fisica` = printed and signed by hand ("Baixar para impressão" +
 * "Marcar como assinado"). The server refuses `enviar` on a `fisica`
 * contract (409 `CONTRATO_FISICO_SEM_ASSINATURA_DIGITAL`) and refuses going
 * `fisica` while an envelope is live (409
 * `CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO`).
 */
export type ModalidadeAssinatura = "digital" | "fisica";

export const MODALIDADE_ASSINATURA_LABEL: Record<ModalidadeAssinatura, string> = {
  digital: "Digital",
  fisica: "Física",
};

/**
 * §2's migration widens ONLY `atendimento_contrato_versoes.origem`'s CHECK,
 * not the contract's own `ContratoOrigem` — a contract does not become
 * "assinado" just because one of its versions did; `ContratoOut.origem` still
 * only ever answers "did this contract start as an upload or a generation".
 */
export type VersaoOrigem = ContratoOrigem | "assinado";

/** Who touched the record last — same shape as the financiamento actor. */
export interface ContratoActor {
  id: string;
  nome: string | null;
}

export interface VersaoOut {
  id: string;
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
  tipo_documento: string;
  enviado_por: ContratoActor | null;
  created_at: string;
  numero: number;
  rotulo: string | null;
  origem: VersaoOrigem;
  /** Migration 120. Only ever `true` on a `gerado` version — the editable
   *  .docx the ABNT PDF was rendered from, stored as a sibling artifact on
   *  the same row. Drives whether "Baixar .docx" renders at all. */
  docx_disponivel: boolean;
  /** Migration 157. For a `gerado` version: the modalidade it was RENDERED
   *  with — only a `fisica` rendering carries the signature lines, so only
   *  that one is offered as "Baixar para impressão". `null` for upload /
   *  assinado versions and for gerado ones that predate the migration. */
  modalidade_assinatura: ModalidadeAssinatura | null;
}

export interface ContratoOut {
  id: string;
  atendimento_id: string;
  titulo: string;
  modelo: ContratoModelo;
  status: ContratoStatus;
  status_em: string | null;
  status_por: ContratoActor | null;
  origem: ContratoOrigem;
  created_at: string;
  // Null until the first new version or PATCH — a freshly created contract
  // has never been updated.
  updated_at: string | null;
  versao_atual: VersaoOut | null;
  versoes: VersaoOut[];
  /** Migration 114. `YYYY-MM-DD`, or `null` (not set yet). */
  assinatura_data: string | null;
  /** Migration 114. `null` = the office default (10 days) — never rendered
   *  as "0" or blank, see `ContratosPanel`'s placeholder. */
  prazo_pendencias_dias: number | null;
  /** Migration 151 (owner directive 2026-09-22) — an explicit, admin-only,
   *  logged flag: this deal started before the platform, so the contract
   *  gate's certidão TIME rules become warnings instead of blocks. NEVER
   *  inferred from a date — set only through `PUT .../processo-legado`. */
  processo_legado: boolean;
  processo_legado_por: ContratoActor | null;
  processo_legado_em: string | null;
  processo_legado_motivo: string | null;
  /** Migration 157 — the signing gate. A pre-157 contract reads `digital`. */
  modalidade_assinatura: ModalidadeAssinatura;
}

export interface ContratoPatch {
  titulo?: string;
  modelo?: ContratoModelo;
  status?: ContratoStatus;
  /** Migration 114. `YYYY-MM-DD`; `null`/`""` clears it. */
  assinatura_data?: string | null;
  /** Migration 114. Must be `> 0` when set; `null` restores the office
   *  default (10 days) — the service's own 400, not a 422. */
  prazo_pendencias_dias?: number | null;
  /** Migration 157. 409 `CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO` when
   *  switching to `fisica` under a live envelope. */
  modalidade_assinatura?: ModalidadeAssinatura;
}

/**
 * The one place a version is "the print copy" of a física contract: a
 * GENERATED version rendered with `fisica` (so it carries the signature
 * lines). A version generated while the contract was still digital is never
 * handed out for printing — it would print the digital-signature clause.
 */
export function versaoParaImpressao(contrato: ContratoOut): VersaoOut | null {
  const atual = contrato.versao_atual;
  if (atual && atual.origem === "gerado" && atual.modalidade_assinatura === "fisica") {
    return atual;
  }
  return null;
}

// ─── Contract generation (F5) ────────────────────────────────────────────
// GET/.../geracao is a READINESS CHECK, not a mutation — the corretor opens
// the section to see what is missing before anything is written. POST
// /.../gerar is the one write, producing a new VERSAO with `origem: "gerado"`
// in the SAME list `useContratos` already renders (see the module header:
// a generated contract is not a second surface).

export type GeracaoModelo = Extract<
  ContratoModelo,
  "compra_venda" | "compra_venda_a_vista" | "compra_venda_permuta"
>;

/** Where a missing field lives — drives the pt-BR group headers on the
 *  "Gerar contrato" section so "falta X" always says where to go fill it. */
export type GeracaoOnde =
  | "partes"
  | "certidoes"
  | "imovel"
  | "matricula"
  | "negociacao"
  | "financiamento"
  | "imobiliaria"
  | "contrato";

export interface GeracaoFaltando {
  campo: string;
  rotulo: string;
  onde: GeracaoOnde;
  parte_id: string | null;
}

export interface GeracaoBloqueio {
  codigo: string;
  mensagem: string;
}

export interface GeracaoAviso {
  codigo: string;
  mensagem: string;
}

export interface ContratoGeracaoStatus {
  contrato_id: string;
  pronto: boolean;
  modelo_derivado: GeracaoModelo;
  /** `false` = the derived model disagrees with the contract's own `modelo`
   *  — shown as a flag, never silently overridden. */
  modelo_confere: boolean;
  /** `true` = a contract started by "Gerar contrato": generating sets its
   *  `modelo` to `modelo_derivado`. `false` = an upload — only flagged. */
  modelo_automatico: boolean;
  /** Migration 151 — mirrors `ContratoOut.processo_legado`, so the "Gerar
   *  contrato" section can show the dispensation is active even before a
   *  reader gets down to the avisos that name it. */
  processo_legado: boolean;
  /** Migration 157 — which instrument `gerar` will render. */
  modalidade_assinatura: ModalidadeAssinatura;
  switches: Record<string, boolean>;
  faltando: GeracaoFaltando[];
  bloqueios: GeracaoBloqueio[];
  avisos: GeracaoAviso[];
}

export interface GerarContratoInput {
  /** `YYYY-MM-DD`. Absent = the backend's own default. */
  assinatura_data?: string;
}

export interface GerarContratoResult {
  /** Same version-row shape the contratos list returns, `origem: "gerado"`. */
  versao: VersaoOut;
  avisos: GeracaoAviso[];
}

/** `POST .../contratos/gerar` — the card's "Gerar contrato" button: the new
 *  (versionless, `origem: "gerado"`) contract plus its readiness report. */
export interface IniciarContratoResult {
  contrato: ContratoOut;
  geracao: ContratoGeracaoStatus;
}

interface ContratoIncompletoDetails {
  faltando?: GeracaoFaltando[];
  bloqueios?: GeracaoBloqueio[];
  /** `422 CONTRATO_LINT`: the rendered text failed the final check (clause
   *  numbering, references, extenso…); nothing was saved. */
  lint?: GeracaoBloqueio[];
}

/**
 * Thrown by `useContratoMutations().gerar` on the 400 `CONTRATO_INCOMPLETO`
 * shape: the typed view of the seed `ApiError`'s `code` + `details`, so the
 * panel shows `details.{faltando,bloqueios}` without a second round trip.
 */
export class ContratoGeracaoError extends Error {
  readonly code: string;
  readonly details: ContratoIncompletoDetails | null;
  constructor(code: string, message: string, details: ContratoIncompletoDetails | null) {
    super(message);
    this.name = "ContratoGeracaoError";
    this.code = code;
    this.details = details;
    // Restore prototype chain, same discipline as the seed `ApiError`.
    Object.setPrototypeOf(this, ContratoGeracaoError.prototype);
  }
}

// ─── Assinatura digital (signature-integration-CONTRACT §3) ───────────────
// One provider today (D4Sign); the shapes below are §3's request/response
// bodies verbatim. The webhook (§3.4) is backend-only — nothing here calls
// it; the FE re-fetches `assinatura` after its own mutations and otherwise
// treats OUR table as the source of truth, never the provider (§3.2: "never
// calls the provider").

export type PapelSignatario =
  | "comprador"
  | "vendedor"
  | "testemunha"
  | "interveniente"
  | "intermediario";

export type StatusAssinatura = "pendente" | "parcial" | "concluido" | "cancelado" | "expirado";

export const PAPEL_SIGNATARIO_LABEL: Record<PapelSignatario, string> = {
  comprador: "Comprador",
  vendedor: "Vendedor",
  testemunha: "Testemunha",
  interveniente: "Interveniente",
  intermediario: "Intermediário",
};

export const STATUS_ASSINATURA_LABEL: Record<StatusAssinatura, string> = {
  pendente: "Pendente",
  parcial: "Parcialmente assinado",
  concluido: "Assinado",
  cancelado: "Cancelado",
  expirado: "Expirado",
};

/** §3.1 request row. The CPF must already be digits-only before this is
 *  sent — the dialog normalizes it; this type does not re-validate it. */
export interface SignatarioInput {
  nome: string;
  email: string;
  cpf: string;
  papel: PapelSignatario;
  ordem?: number;
  /** [papel="testemunha" only, migration 168] The `org_testemunhas` row this
   *  signatário was selected from — lets the server re-resolve the
   *  authoritative e-mail/cpf by id (`assinatura_service._resolver_
   *  testemunhas_do_registro`) instead of a nome match. Omitted for every
   *  other papel. */
  testemunha_id?: string;
}

/** §3.1/§3.2 response row — one signer's progress. */
export interface SignatarioRemoto {
  email: string;
  external_id: string;
  assinado_em: string | null;
}

/**
 * §3.1 201 / §3.2 200 body. `concluido_em`/`versao_assinada_id`/
 * `cancelado_motivo` are only ever populated on the §3.2 GET (a fresh §3.1
 * 201 is always `pendente`) — typed optional rather than split into two
 * interfaces, same discipline as `ContratoOut.updated_at`.
 */
export interface AssinaturaOut {
  assinatura_id: string;
  external_id: string;
  link_assinatura: string;
  provedor: string;
  status: StatusAssinatura;
  signatarios: SignatarioRemoto[];
  enviado_em: string;
  concluido_em?: string | null;
  versao_assinada_id?: string | null;
  cancelado_motivo?: string | null;
}

export interface EnviarParaAssinaturaInput {
  contratoId: string;
  versaoId: string;
  signatarios: SignatarioInput[];
  /** <= 500 chars per §3.1; empty/omitted sends nothing. */
  mensagem?: string;
}

export interface CancelarAssinaturaInput {
  contratoId: string;
  /** 3..500 chars per §3.3 — the caller validates before calling. */
  motivo: string;
}

interface AssinaturaErrorDetails {
  /** 422 `ASSINATURA_PROVEDOR_NAO_CONFIGURADO`: which credentials are missing. */
  faltando?: string[];
  /** 502 `ASSINATURA_PROVEDOR_ERRO`: the provider's own refusal text. */
  provedor_mensagem?: string;
}

/**
 * Thrown by `enviarParaAssinatura`/`cancelarAssinatura` on every non-2xx
 * §3.1/§3.2/§3.3 response — `ContratoGeracaoError`'s sibling, the typed view
 * of the seed `ApiError`'s `code` + `details` so a caller reads them without
 * a second round trip. `message` is the server's own pt-BR sentence (§3.1's
 * error table), never a hand-rolled copy that could drift from it.
 */
export class AssinaturaError extends Error {
  readonly code: string;
  readonly details: AssinaturaErrorDetails | null;
  constructor(code: string, message: string, details: AssinaturaErrorDetails | null) {
    super(message);
    this.name = "AssinaturaError";
    this.code = code;
    this.details = details;
    // Restore prototype chain, same discipline as the seed `ApiError`.
    Object.setPrototypeOf(this, AssinaturaError.prototype);
  }
}

/** `status in ('pendente','parcial')` — the ONE thing migration 134's partial
 *  unique index enforces per contract. Everything in §4 that gates on "is
 *  there a LIVE envelope" (hiding "Enviar para assinatura", showing the
 *  pendente/parcial block + "Cancelar envio") reads this, never bare
 *  truthiness — a `concluido`/`cancelado`/`expirado` row is still a real
 *  `AssinaturaOut`, not `null`, and must not read as "still in flight". The
 *  DISABLED-status-select rule is deliberately different: it reads "does an
 *  envelope exist AT ALL" (`!!assinatura`), because the manual
 *  `enviado_assinatura`/`assinado` picks are retired for good the moment a
 *  contract enters this flow, not just while a send is in flight.
 */
export function envelopeVivo(assinatura: AssinaturaOut | null | undefined): boolean {
  return assinatura?.status === "pendente" || assinatura?.status === "parcial";
}

export const STATUS_LABEL: Record<ContratoStatus, string> = {
  rascunho: "Rascunho",
  em_revisao: "Em revisão",
  enviado_assinatura: "Enviado p/ assinatura",
  assinado: "Assinado",
  cancelado: "Cancelado",
};

export const MODELO_LABEL: Record<ContratoModelo, string> = {
  compra_venda: "Compra e venda",
  compra_venda_permuta: "Compra e venda com permuta",
  compra_venda_a_vista: "Compra e venda à vista",
  outro: "Outro",
};

export const CONTRATO_STATUS_OPTIONS: ContratoStatus[] = [
  "rascunho",
  "em_revisao",
  "enviado_assinatura",
  "assinado",
  "cancelado",
];

export const CONTRATO_MODELO_OPTIONS: ContratoModelo[] = [
  "compra_venda",
  "compra_venda_permuta",
  "compra_venda_a_vista",
  "outro",
];

// ─── Client-side upload validation ─────────────────────────────────────────
// Mirrors the server's own gate (422 for wrong MIME / oversize) so the user
// finds out from the form, not from a round trip.

/** Migration 157 — the scanned signed copy of a física contract: PDF only
 *  (the server's own 400 otherwise), same 25 MB ceiling. */
export const CONTRATO_ASSINADO_ACCEPT_ATTR = ".pdf,application/pdf";

export function validateContratoAssinadoFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return `Envie o contrato assinado digitalizado em PDF (${file.name} não é PDF).`;
  }
  if (file.size > MAX_BYTES) {
    return `Arquivo muito grande (${formatBytes(file.size)}). O limite é 25 MB.`;
  }
  return null;
}

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".doc"] as const;
export const CONTRATO_ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");
const MAX_BYTES = 25 * 1024 * 1024;

export function validateContratoFile(file: File): string | null {
  const lower = file.name.toLowerCase();
  const okExt = ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  if (!okExt) {
    return `Formato não suportado: ${file.name}. Aceitos: PDF, DOCX, DOC.`;
  }
  if (file.size > MAX_BYTES) {
    return `Arquivo muito grande (${formatBytes(file.size)}). O limite é 25 MB.`;
  }
  return null;
}

export { formatBytes };

// ─── Keys ───────────────────────────────────────────────────────────────────

const KEY = (clienteId: string) => ["sw", "clientes", clienteId, "contratos"] as const;

const GERACAO_KEY = (clienteId: string, contratoId: string) =>
  [...KEY(clienteId), contratoId, "geracao"] as const;

const base = (clienteId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/contratos`;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useContratos(clienteId: string | null) {
  return useQuery({
    queryKey: KEY(clienteId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<{ contratos: ContratoOut[] }>(base(clienteId as string));
      return res?.contratos ?? [];
    },
    enabled: !!clienteId,
  });
}

/**
 * useContratoGeracao — GET .../geracao.
 *
 * 🔴 `enabled` IS THE LAZY GATE, not just `!!contratoId`. Unlike the acts
 * selection matrícula section, this readiness check is opt-in per the F5
 * brief: the caller passes `aberto` (whether the "Gerar contrato" collapsible
 * is open) so the check fires only once a corretor actually looks, not for
 * every contract on the card the moment it renders.
 */
export function useContratoGeracao(
  clienteId: string | null,
  contratoId: string | null,
  aberto: boolean,
) {
  return useQuery({
    queryKey: GERACAO_KEY(clienteId ?? "__none__", contratoId ?? "__none__"),
    queryFn: () =>
      api.get<ContratoGeracaoStatus>(
        `${base(clienteId as string)}/${encodeURIComponent(contratoId as string)}/geracao`,
      ),
    enabled: aberto && !!clienteId && !!contratoId,
  });
}

const ASSINATURA_KEY = (clienteId: string, contratoId: string) =>
  [...KEY(clienteId), contratoId, "assinatura"] as const;

/**
 * §3.2 GET, with the ONE translation the FE owns: a 404
 * `ASSINATURA_NAO_ENCONTRADA` means "never sent" — the expected shape of "no
 * data", not an error state — so it resolves to `null` rather than rejecting.
 * Anything else (network, 5xx) is a real query error.
 */
async function fetchAssinatura(
  clienteId: string,
  contratoId: string,
): Promise<AssinaturaOut | null> {
  try {
    return await api.get<AssinaturaOut>(
      `${base(clienteId)}/${encodeURIComponent(contratoId)}/assinatura`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export interface AssinaturaEntry {
  /** `undefined` = not yet resolved. `null` = resolved, no envelope ever
   *  sent. A value = the most recent envelope regardless of status — see
   *  `envelopeVivo` for "is it live right now". */
  data: AssinaturaOut | null | undefined;
  isPending: boolean;
  isFetching: boolean;
  isError: boolean;
}

/**
 * One §3.2 GET per contract that could ever have gone through the signature
 * flow. The caller (`ContratosContainer`) passes only the ids whose
 * `versoes` include an `origem: "gerado"` row — an upload-only contract
 * never fires a request that can only ever 404.
 *
 * `useQueries`, not a `.map()` of `useQuery`: `contratoIds.length` changes
 * across renders (a card can gain a generated version), and a variable
 * number of `useQuery` calls breaks the rules of hooks.
 */
export function useAssinaturas(
  clienteId: string | null,
  contratoIds: string[],
): Record<string, AssinaturaEntry> {
  const results = useQueries({
    queries: contratoIds.map((contratoId) => ({
      queryKey: ASSINATURA_KEY(clienteId ?? "__none__", contratoId),
      queryFn: () => fetchAssinatura(clienteId as string, contratoId),
      enabled: !!clienteId,
    })),
  });
  const byContrato: Record<string, AssinaturaEntry> = {};
  contratoIds.forEach((contratoId, i) => {
    const r = results[i] as
      | { data?: AssinaturaOut | null; isPending?: boolean; isFetching?: boolean; isError?: boolean }
      | undefined;
    byContrato[contratoId] = {
      data: r?.data,
      isPending: !!r?.isPending,
      isFetching: !!r?.isFetching,
      isError: !!r?.isError,
    };
  });
  return byContrato;
}

// ─── Mutations ──────────────────────────────────────────────────────────────

async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** POST multipart, JSON response. The one place raw `fetch` is needed —
 *  the seed `api` client is JSON-only. */
async function postMultipart(url: string, formData: FormData): Promise<ContratoOut> {
  const headers = await getAuthHeader();
  const response = await fetch(apiUrl(url), {
    method: "POST",
    headers, // no content-type — the browser sets the multipart boundary
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await extractDetailMessage(response));
  }
  return (await response.json()) as ContratoOut;
}

/**
 * The server's own `detail` — the ONE surface for every failure this hook
 * can hit: the 400/422 DocumentoStore file gate (wrong MIME / oversize) AND
 * the 409 `AmbiguousAtendimento` every contratos route inherits from
 * financiamento's same `cliente_id` resolution. Both carry `detail`, so
 * neither status is special-cased — they are shown identically, the same
 * way `@noctusai/lib/api`'s client already reads it for the JSON mutations.
 *
 * FastAPI's own 422 shape sends `detail` as an ARRAY of pydantic error
 * objects rather than a string — handled the same way the seed `api`
 * client's `extractErrorMessage` does, so a validation failure never falls
 * back to a bare "Erro HTTP 422".
 */
async function extractDetailMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  // A typed `AppException` (e.g. migration 157's 409s) answers
  // `{error: {code, message}}`, not FastAPI's `detail` — its pt-BR
  // `message` is the sentence to show.
  const appMessage = body?.error?.message;
  if (typeof appMessage === "string" && appMessage) return appMessage;
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const joined = detail.map((e) => e?.msg ?? e?.message).filter(Boolean).join("; ");
    if (joined) return joined;
  }
  return `Erro HTTP ${response.status}`;
}

/**
 * POST through the seed `api` client (auth, 401 refresh, error extraction),
 * translating its `ApiError` into `ContratoGeracaoError` so the readiness
 * section reads `code` + `details.{faltando,bloqueios}` from the 400
 * `CONTRATO_INCOMPLETO` body — which `ApiError` now carries as `body`.
 */
async function postGerarContrato(
  url: string,
  body: GerarContratoInput,
): Promise<GerarContratoResult> {
  try {
    return await api.post<GerarContratoResult>(url, body);
  } catch (err) {
    if (err instanceof ApiError) {
      const envelope = err.body as { error?: { message?: string } } | undefined;
      throw new ContratoGeracaoError(
        err.code ?? "erro_desconhecido",
        envelope?.error?.message ?? err.message,
        (err.details as ContratoIncompletoDetails | null) ?? null,
      );
    }
    throw err;
  }
}

/**
 * POST through the seed `api` client, translating its `ApiError` into
 * `AssinaturaError` so `enviarParaAssinatura`/`cancelarAssinatura` callers
 * read `code`/`details.{faltando,provedor_mensagem}` from the §3.1/§3.3
 * error bodies. `message` prefers the server's own `error.message` over
 * `ApiError.message` — the latter carries the `[status]` prefix — same
 * discipline as `postGerarContrato`.
 */
async function postAssinatura<T>(url: string, body: unknown): Promise<T> {
  try {
    return await api.post<T>(url, body);
  } catch (err) {
    if (err instanceof ApiError) {
      const envelope = err.body as { error?: { message?: string } } | undefined;
      throw new AssinaturaError(
        err.code ?? "erro_desconhecido",
        envelope?.error?.message ?? err.message,
        (err.details as AssinaturaErrorDetails | null) ?? null,
      );
    }
    throw err;
  }
}

export function useContratoMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: KEY(clienteId) });

  const create = useMutation({
    mutationFn: async ({
      file,
      titulo,
      modelo,
      rotulo,
    }: {
      file: File;
      titulo: string;
      modelo?: ContratoModelo;
      rotulo?: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("titulo", titulo);
      if (modelo) formData.append("modelo", modelo);
      if (rotulo) formData.append("rotulo", rotulo);
      return postMultipart(base(clienteId), formData);
    },
    onSuccess: invalidate,
  });

  const addVersao = useMutation({
    mutationFn: async ({
      contratoId,
      file,
      rotulo,
    }: {
      contratoId: string;
      file: File;
      rotulo?: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      if (rotulo) formData.append("rotulo", rotulo);
      return postMultipart(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}/versoes`,
        formData,
      );
    },
    onSuccess: invalidate,
  });

  const patch = useMutation({
    mutationFn: ({ contratoId, patch: body }: { contratoId: string; patch: ContratoPatch }) =>
      api.patch<ContratoOut>(`${base(clienteId)}/${encodeURIComponent(contratoId)}`, body),
    onSuccess: invalidate,
  });

  const deleteVersao = useMutation({
    mutationFn: ({
      contratoId,
      versaoId,
      motivo,
    }: {
      contratoId: string;
      versaoId: string;
      motivo: string;
    }) =>
      api.delete(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}/versoes/${encodeURIComponent(versaoId)}?motivo=${encodeURIComponent(motivo)}`,
      ),
    onSuccess: invalidate,
  });

  const deleteContrato = useMutation({
    mutationFn: ({ contratoId, motivo }: { contratoId: string; motivo: string }) =>
      api.delete(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}?motivo=${encodeURIComponent(motivo)}`,
      ),
    onSuccess: invalidate,
  });

  /** 🔴 Same shape as `useFinanciamentoDocumentoMutations.getUrl` — call only
   *  on an explicit "Abrir"/"Baixar" click, never speculatively.
   *
   *  `formato` (migration 120) is omitted from the query string unless it is
   *  `"docx"` — the backend already defaults `formato=pdf`, so every
   *  pre-existing "Abrir"/"Baixar" call site stays byte-identical. */
  const getUrl = useMutation({
    mutationFn: ({
      contratoId,
      versaoId,
      intent = "view",
      formato,
    }: {
      contratoId: string;
      versaoId: string;
      intent?: "view" | "download";
      formato?: "pdf" | "docx";
    }) =>
      api.get<{ url: string; expires_at: string }>(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}/versoes/${encodeURIComponent(versaoId)}/url?intent=${intent}${formato === "docx" ? "&formato=docx" : ""}`,
      ),
  });

  /**
   * `gerar` — POST .../gerar. On success invalidates BOTH the contratos list
   * (the new `origem: "gerado"` version has to show up where every other
   * version does) and this contract's `geracao` query (a fresh check after
   * the write, not the stale pre-generation one).
   */
  const gerar = useMutation({
    mutationFn: ({
      contratoId,
      assinaturaData,
    }: {
      contratoId: string;
      assinaturaData?: string;
    }) =>
      postGerarContrato(`${base(clienteId)}/${encodeURIComponent(contratoId)}/gerar`, {
        assinatura_data: assinaturaData,
      }),
    onSuccess: (_data, variables) => {
      invalidate();
      qc.invalidateQueries({ queryKey: GERACAO_KEY(clienteId, variables.contratoId) });
    },
  });

  /**
   * `iniciar` — POST .../contratos/gerar. Creates the contract to generate
   * (the matrícula acts are chosen per contract, so it must exist first) and
   * seeds its `geracao` query with the readiness report that came back, so
   * the card opens on "what is missing" without a second request.
   */
  const iniciar = useMutation({
    mutationFn: () => api.post<IniciarContratoResult>(`${base(clienteId)}/gerar`, {}),
    onSuccess: (data) => {
      qc.setQueryData(GERACAO_KEY(clienteId, data.contrato.id), data.geracao);
      invalidate();
    },
  });

  /**
   * `enviarParaAssinatura` — POST §3.1. Seeds the `assinatura` cache with the
   * fresh 201 body (no need to wait on a refetch to show the pendente chip)
   * and invalidates the contratos list: §3.1's side-effect 3 says
   * `atendimento_contratos.status` is ALREADY `enviado_assinatura` when this
   * returns — the FE never sets it itself.
   */
  const enviarParaAssinatura = useMutation({
    mutationFn: ({ contratoId, versaoId, signatarios, mensagem }: EnviarParaAssinaturaInput) =>
      postAssinatura<AssinaturaOut>(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}/assinatura`,
        {
          versao_id: versaoId,
          signatarios: signatarios.map((s) => ({
            nome: s.nome,
            email: s.email,
            cpf: s.cpf,
            papel: s.papel,
            ordem: s.ordem ?? 0,
          })),
          mensagem: mensagem?.trim() ? mensagem.trim() : undefined,
        },
      ),
    onSuccess: (data, variables) => {
      qc.setQueryData(ASSINATURA_KEY(clienteId, variables.contratoId), data);
      invalidate();
    },
  });

  /**
   * `cancelarAssinatura` — POST §3.3. §3.3's state-after returns
   * `atendimento_contratos.status` to `em_revisao` — same reason `invalidate`
   * runs here as it does on `enviarParaAssinatura`.
   */
  const cancelarAssinatura = useMutation({
    mutationFn: ({ contratoId, motivo }: CancelarAssinaturaInput) =>
      postAssinatura<AssinaturaOut>(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}/assinatura/cancelar`,
        { motivo },
      ),
    onSuccess: (data, variables) => {
      qc.setQueryData(ASSINATURA_KEY(clienteId, variables.contratoId), data);
      invalidate();
    },
  });

  /**
   * `processoLegado` — PUT .../processo-legado (migration 151, owner
   * directive 2026-09-22). Admin-only server-side (403 for anyone else);
   * on success invalidates BOTH the contratos list (the badge/checkbox
   * read off `ContratoOut.processo_legado`) and this contract's `geracao`
   * query (the dispensed avisos only show up after a fresh readiness
   * check), same pairing `gerar` already uses.
   */
  const processoLegado = useMutation({
    mutationFn: ({
      contratoId,
      ativo,
      motivo,
    }: {
      contratoId: string;
      ativo: boolean;
      motivo?: string;
    }) =>
      api.put<ContratoOut>(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}/processo-legado`,
        { ativo, motivo },
      ),
    onSuccess: (_data, variables) => {
      invalidate();
      qc.invalidateQueries({ queryKey: GERACAO_KEY(clienteId, variables.contratoId) });
    },
  });

  /**
   * `marcarAssinadoFisico` — POST .../assinatura-fisica (migration 157). A
   * `fisica` contract's manual close-out: status `assinado` (stamped by the
   * server) plus, optionally, the scanned signed PDF as a new `assinado`
   * version. Multipart because of the optional file — `postMultipart`
   * surfaces the server's own pt-BR message on every refusal.
   */
  const marcarAssinadoFisico = useMutation({
    mutationFn: ({ contratoId, file }: { contratoId: string; file?: File | null }) => {
      const formData = new FormData();
      if (file) formData.append("file", file);
      return postMultipart(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}/assinatura-fisica`,
        formData,
      );
    },
    onSuccess: invalidate,
  });

  return {
    create,
    addVersao,
    patch,
    deleteVersao,
    deleteContrato,
    getUrl,
    gerar,
    iniciar,
    enviarParaAssinatura,
    cancelarAssinatura,
    processoLegado,
    marcarAssinadoFisico,
  };
}

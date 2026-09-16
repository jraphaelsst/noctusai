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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  origem: ContratoOrigem;
  /** Migration 120. Only ever `true` on a `gerado` version — the editable
   *  .docx the ABNT PDF was rendered from, stored as a sibling artifact on
   *  the same row. Drives whether "Baixar .docx" renders at all. */
  docx_disponivel: boolean;
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

  return { create, addVersao, patch, deleteVersao, deleteContrato, getUrl, gerar };
}

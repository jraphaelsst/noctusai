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
}

export interface ContratoPatch {
  titulo?: string;
  modelo?: ContratoModelo;
  status?: ContratoStatus;
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
   *  on an explicit "Abrir"/"Baixar" click, never speculatively. */
  const getUrl = useMutation({
    mutationFn: ({
      contratoId,
      versaoId,
      intent = "view",
    }: {
      contratoId: string;
      versaoId: string;
      intent?: "view" | "download";
    }) =>
      api.get<{ url: string; expires_at: string }>(
        `${base(clienteId)}/${encodeURIComponent(contratoId)}/versoes/${encodeURIComponent(versaoId)}/url?intent=${intent}`,
      ),
  });

  return { create, addVersao, patch, deleteVersao, deleteContrato, getUrl };
}

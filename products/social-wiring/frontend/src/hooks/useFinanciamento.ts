/**
 * Financiamento / Escritura — the deal's closing paperwork (migration 078).
 *
 * 🔴 THESE DOCUMENTS ARE ACCESS-LOGGED SERVER-SIDE.
 * Opening one mints a signed URL, and that call appends to
 * `atendimento_documento_acessos` naming the user. So the UI must never
 * pre-fetch a URL "just in case" or refresh one on a timer: every fetch is a
 * recorded access to somebody's income tax return, and a log full of accesses
 * nobody made is worse than no log.
 *
 * `useDocumentoAcessos` is therefore lazy — enabled only when a viewer
 * actually opens the log.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, supabase } from "@noctusai/seed/infra";

import { apiUrl } from "@/lib/apiBase";

// ─── Types ──────────────────────────────────────────────────────────────────

export type SituacaoFinanciamento = "pendente" | "aprovado" | "recusado";

export interface FinanciamentoDocumento {
  id: string;
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
  tipo_documento: string;
  /** `"escritura"` | `"fgts"` — the section this belongs in, server-decided. */
  grupo: string;
  categoria_lgpd: string | null;
  retencao_ate: string | null;
  enviado_por: { id: string; nome: string | null } | null;
  created_at: string;
}

export interface Financiamento {
  atendimento_id: string;
  situacao: SituacaoFinanciamento;
  situacao_em: string | null;
  situacao_motivo: string | null;
  fgts: boolean;
  observacoes: string | null;
  created_at: string | null;
  updated_at: string | null;
  existe: boolean;
  /** The document types each section offers, in order. Server-owned. */
  tipos_escritura: string[];
  tipos_fgts: string[];
  documentos: FinanciamentoDocumento[];
}

export interface FinanciamentoPatch {
  situacao?: SituacaoFinanciamento;
  situacao_motivo?: string | null;
  fgts?: boolean;
  observacoes?: string | null;
}

export interface Acesso {
  id: string;
  acao: string;
  usuario: { id: string; nome: string | null } | null;
  created_at: string;
}

/** Human labels for the document types. The KEYS are the server's contract. */
export const TIPO_LABEL: Record<string, string> = {
  certidao_casamento: "Certidão de casamento",
  escritura_pacto: "Escritura do pacto",
  registro_pacto: "Registro do pacto",
  comprovante_residencia: "Comprovante de residência",
  imposto_renda_com_recibo: "Imposto de renda (com recibo de entrega)",
  carteira_trabalho: "Carteira de trabalho",
  extratos_fgts: "Extratos do FGTS",
  comprovante_residencia_1ano: "Comprovante de residência (há 1 ano)",
};

export const SITUACAO_LABEL: Record<SituacaoFinanciamento, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  recusado: "Recusado",
};

// ─── Keys ───────────────────────────────────────────────────────────────────

const KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "financiamento"] as const;
const ACESSOS_KEY = (clienteId: string, docId: string) =>
  [...KEY(clienteId), "acessos", docId] as const;

const base = (clienteId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/financiamento`;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useFinanciamento(clienteId: string | null) {
  return useQuery({
    queryKey: KEY(clienteId ?? "__none__"),
    queryFn: async () => api.get<Financiamento>(base(clienteId as string)),
    enabled: !!clienteId,
  });
}

export function useFinanciamentoAcessos(
  clienteId: string | null,
  documentoId: string | null,
) {
  return useQuery({
    queryKey: ACESSOS_KEY(clienteId ?? "__none__", documentoId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<{ items: Acesso[]; total: number }>(
        `${base(clienteId as string)}/documentos/${encodeURIComponent(
          documentoId as string,
        )}/acessos`,
      );
      return res?.items ?? [];
    },
    // Lazy on purpose — the log is opened, not polled. Reading it is itself
    // free (metadata, not content), but fetching it unasked is noise.
    enabled: !!clienteId && !!documentoId,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function useFinanciamentoMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: FinanciamentoPatch) =>
      api.patch<Financiamento>(base(clienteId), patch),
    onSuccess: (data) => qc.setQueryData(KEY(clienteId), data),
  });
}

export function useFinanciamentoDocumentoMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: KEY(clienteId) });

  // Multipart bypasses the JSON-only seed `api` client — raw fetch with the
  // auth header pulled from supabase.
  const upload = useMutation({
    mutationFn: async ({
      file,
      tipoDocumento,
    }: {
      file: File;
      tipoDocumento: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("tipo_documento", tipoDocumento);
      const headers = await getAuthHeader();
      const response = await fetch(apiUrl(`${base(clienteId)}/documentos`), {
        method: "POST",
        headers, // no content-type — the browser sets the multipart boundary
        body: formData,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        const message = detail?.error?.message ?? `Erro HTTP ${response.status}`;
        throw new Error(message);
      }
      return (await response.json()) as FinanciamentoDocumento;
    },
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: ({
      documentoId,
      motivo,
    }: {
      documentoId: string;
      motivo: string;
    }) =>
      api.delete(
        `${base(clienteId)}/documentos/${encodeURIComponent(documentoId)}?motivo=${encodeURIComponent(motivo)}`,
      ),
    onSuccess: invalidate,
  });

  /** 🔴 Each call is a RECORDED access. Never call this speculatively. */
  const getUrl = useMutation({
    mutationFn: ({
      documentoId,
      intent = "view",
    }: {
      documentoId: string;
      intent?: "view" | "download";
    }) =>
      api.get<{ url: string; expires_at: string }>(
        `${base(clienteId)}/documentos/${encodeURIComponent(documentoId)}/url?intent=${intent}`,
      ),
  });

  return { upload, remove, getUrl };
}

export function formatBytes(n: number): string {
  const mb = n / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${Math.round(n / 1024)} KB`;
}

/**
 * Imóvel cartório data + documents — `/api/imoveis/{codigo}/...`.
 *
 * Deliberately a separate file from `useImoveis.ts`, mirroring the split the
 * backend and migration 075 both make: `useImoveis` reads the Vista sync
 * MIRROR, this reads what WE author. Same reason, one level up — a single
 * hook file invites a single query key, and invalidating "imoveis" after a
 * cartório edit would re-fetch the whole 1919-imóvel catalog.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, supabase } from "@noctusai/seed/infra";

import { apiUrl } from "@/lib/apiBase";

// ─── Types ──────────────────────────────────────────────────────────────────

/** A resolved user reference — `nome` is null when the id no longer resolves. */
export interface Ator {
  id: string;
  nome: string | null;
}

export interface ImovelDados {
  codigo: string;
  numero_matricula: string | null;
  /** `'manual'` (a human typed it) | `'matricula'` (read off the document). */
  numero_matricula_origem: string | null;
  numero_matricula_documento_id: string | null;
  numero_matricula_em: string | null;
  numero_matricula_confirmado_por: Ator | null;
  numero_matricula_confirmado_em: string | null;
  numero_registro_imoveis: string | null;
  prefeitura_cadastro_imobiliario: string | null;
  captador: Ator | null;

  // ─── Situação de ônus (migration 099) ──────────────────────────────────
  //
  // The first clause of every promessa de compra e venda asserts the property
  // is sold "livre e desembaraçado de quaisquer ônus reais". Until 099 nothing
  // in the schema could back that sentence: `atendimento_financiamento`
  // records the BUYER's financing, which is the opposite side of the
  // transaction from the SELLER's outstanding debt.
  //
  // 🔴 NO RULES ATTACHED YET, on purpose. Nothing refuses to emit a document
  // on a stale certidão and nothing ties these fields to each other — the
  // policy is still the user's to decide, and a gate written before its policy
  // is a gate that gets worked around.
  situacao_onus: string | null;
  onus_observacoes: string | null;
  /** The date printed ON the certidão — NOT the upload timestamp. A certidão's
   *  validity runs from its own emission, so the upload date answers a
   *  different question. */
  onus_certidao_em: string | null;
  onus_documento_id: string | null;
  onus_registrado_por: Ator | null;
  onus_registrado_em: string | null;
  /** The vocabulary the server offers. Sent by the API rather than hard-coded
   *  here so the list has ONE home — it lives in `dados_service`, beside the
   *  column it fills. */
  situacoes_onus: string[];

  updated_at: string | null;
}

/**
 * The fields a human may set.
 *
 * 🔴 `null` is a REAL value (clearing a wrongly-typed matrícula number), and
 * absence is what means "leave alone" — so a patch must send only the keys it
 * intends to change. Never spread a whole `ImovelDados` into this.
 */
export interface ImovelDadosPatch {
  numero_matricula?: string | null;
  numero_registro_imoveis?: string | null;
  prefeitura_cadastro_imobiliario?: string | null;
  captador_user_id?: string | null;
  situacao_onus?: string | null;
  onus_observacoes?: string | null;
  onus_certidao_em?: string | null;
  onus_documento_id?: string | null;
}

export type ExtracaoStatus =
  | "pendente"
  | "processando"
  | "ok"
  | "sem_dados"
  | "erro";

export interface ImovelDocumento {
  id: string;
  codigo: string;
  nome_original: string;
  mime_type: string;
  tamanho_bytes: number;
  tipo_documento: string;
  enviado_por: Ator | null;
  created_at: string;
  extracao_status: ExtracaoStatus | null;
  extracao_matricula: string | null;
  extracao_confianca: string | null;
  extracao_rotulo: string | null;
  extracao_erro: string | null;
}

export interface DocumentoUrlResponse {
  url: string;
  expires_at: string;
}

interface ItemsEnvelope<T> {
  items: T[];
  total: number;
}

/** The document types this surface offers, in the order they are asked for. */
export const TIPOS_DOCUMENTO = [
  { value: "matricula", label: "Matrícula" },
  { value: "guia_iptu", label: "Guia de IPTU" },
] as const;

// ─── Query keys ─────────────────────────────────────────────────────────────

const FAMILY_KEY = (codigo: string) => ["sw", "imovel-dados", codigo] as const;
const DADOS_KEY = (codigo: string) => [...FAMILY_KEY(codigo), "dados"] as const;
const DOCUMENTOS_KEY = (codigo: string) =>
  [...FAMILY_KEY(codigo), "documentos"] as const;

const base = (codigo: string) => `/api/imoveis/${encodeURIComponent(codigo)}`;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useImovelDados(codigo: string | null) {
  return useQuery({
    queryKey: DADOS_KEY(codigo ?? "__none__"),
    queryFn: async () =>
      api.get<ImovelDados>(`${base(codigo as string)}/dados`),
    enabled: !!codigo,
  });
}

export function useImovelDocumentos(codigo: string | null) {
  return useQuery({
    queryKey: DOCUMENTOS_KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<ImovelDocumento>>(
        `${base(codigo as string)}/documentos`,
      );
      return res?.items ?? [];
    },
    enabled: !!codigo,
    /**
     * 🔴 While a matrícula is being read, poll.
     *
     * The read runs as a detached background task, so nothing pushes its
     * result. Without this the user uploads a PDF, sees "lendo…", and the
     * field silently fills only if they happen to reload — which reads as a
     * broken feature rather than a slow one.
     *
     * Polling STOPS as soon as no document is in a non-terminal state, so an
     * idle page makes no requests at all.
     */
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (!docs) return false;
      const trabalhando = docs.some(
        (d) => d.extracao_status === "pendente" || d.extracao_status === "processando",
      );
      return trabalhando ? 3000 : false;
    },
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function useImovelDadosMutation(codigo: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: ImovelDadosPatch) =>
      api.patch<ImovelDados>(`${base(codigo)}/dados`, patch),
    onSuccess: (data) => {
      // Seed the cache from the response rather than only invalidating —
      // the PATCH already returns the full, freshly-read row.
      qc.setQueryData(DADOS_KEY(codigo), data);
    },
  });
}

export function useImovelDocumentoMutations(codigo: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: DOCUMENTOS_KEY(codigo) });
    // An uploaded matrícula can fill `numero_matricula` moments later, so
    // the dados card is stale too.
    qc.invalidateQueries({ queryKey: DADOS_KEY(codigo) });
  };

  // Multipart bypasses the JSON-only seed `api` client — raw fetch with the
  // auth header pulled from supabase, same pattern as `useCardHub`'s upload.
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
      const response = await fetch(apiUrl(`${base(codigo)}/documentos`), {
        method: "POST",
        headers, // no content-type — the browser sets the multipart boundary
        body: formData,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        const message = detail?.error?.message ?? `Erro HTTP ${response.status}`;
        throw new Error(message);
      }
      return (await response.json()) as ImovelDocumento;
    },
    onSuccess: invalidate,
  });

  // `motivo` travels as a REQUIRED query param, not a JSON body — the seed
  // `ApiClient.delete()` has no body parameter.
  const remove = useMutation({
    mutationFn: ({
      documentoId,
      motivo,
    }: {
      documentoId: string;
      motivo: string;
    }) =>
      api.delete(
        `${base(codigo)}/documentos/${encodeURIComponent(documentoId)}?motivo=${encodeURIComponent(motivo)}`,
      ),
    onSuccess: invalidate,
  });

  const getUrl = useMutation({
    mutationFn: (documentoId: string) =>
      api.get<DocumentoUrlResponse>(
        `${base(codigo)}/documentos/${encodeURIComponent(documentoId)}/url`,
      ),
  });

  return { upload, remove, getUrl };
}

// ─── Display helpers ────────────────────────────────────────────────────────

/** Where a stored matrícula number came from, in words. */
export function origemLabel(origem: string | null): string | null {
  if (origem === "manual") return "informado manualmente";
  if (origem === "matricula") return "lido da matrícula";
  return null;
}

export function formatBytes(n: number): string {
  const mb = n / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${Math.round(n / 1024)} KB`;
}

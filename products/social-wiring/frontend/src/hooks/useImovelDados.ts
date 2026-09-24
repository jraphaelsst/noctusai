/**
 * Imóvel cartório data + documents — `/api/imoveis/{codigo}/...`.
 *
 * Deliberately a separate file from `useImoveis.ts`, mirroring the split the
 * backend and migration 075 both make: `useImoveis` reads the Vista sync
 * MIRROR, this reads what WE author. Same reason, one level up — a single
 * hook file invites a single query key, and invalidating "imoveis" after a
 * cartório edit would re-fetch the whole 1919-imóvel catalog.
 */
import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, supabase } from "@noctusai/seed/infra";

import { apiUrl } from "@/lib/apiBase";

// ─── Types ──────────────────────────────────────────────────────────────────

/** A resolved user reference — `nome` is null when the id no longer resolves. */
export interface Ator {
  id: string;
  nome: string | null;
}

/**
 * Where the título aquisitivo pointer came from (migration 109) — offsets
 * only. The literal text lives in the matrícula transcription, served by
 * `GET /api/matriculas/extracoes/{id}/fontes`; this card links there rather
 * than duplicating the quote.
 */
export interface ImovelFonteTituloAquisitivo {
  extracao_id: string;
  ato_id: string;
  char_inicio: number;
  char_fim: number;
  origem: "sugerido" | "manual";
  confirmado_por: Ator | null;
  confirmado_em: string | null;
}

export interface ImovelFonteOnusAtoRef {
  ato_id: string;
  char_inicio: number;
  char_fim: number;
}

/** The ônus source pointer (migration 109) — offsets only, same reason. */
export interface ImovelFonteOnus {
  extracao_id: string;
  atos: ImovelFonteOnusAtoRef[];
  origem: "sugerido" | "manual";
  confirmado_por: Ator | null;
  confirmado_em: string | null;
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

  // ─── Título aquisitivo / ônus sources (migration 109) ──────────────────
  // Pointers only — `null` until the operator confirms one on the matrícula
  // page (`GET /api/matriculas/extracoes/{id}/fontes`). Never written by the
  // PATCH route on this card; read-only here by construction.
  titulo_aquisitivo_fonte: ImovelFonteTituloAquisitivo | null;
  onus_fonte: ImovelFonteOnus | null;

  // ─── Manual address override (migration 149, widened by 159) ───────────
  // All 7 `Endereco` fields — this product has no write-back to the Vista
  // mirror those normally come from. `null` on every field means "use the
  // mirror". Written ONLY by `PUT .../endereco-manual`
  // (`useEnderecoManualMutation`) or at registration time
  // (`useRegistrarImovelManual`, `hooks/useImovelRegistro.ts`), never by the PATCH route
  // above. `complemento`/`bairro`/`cep` (159) let an operator override a
  // condo UNIT's full address when Vista mirrors only the building's gate.
  endereco_manual_logradouro: string | null;
  endereco_manual_numero: string | null;
  endereco_manual_complemento: string | null;
  endereco_manual_bairro: string | null;
  endereco_manual_cidade: string | null;
  endereco_manual_uf: string | null;
  endereco_manual_cep: string | null;
  endereco_manual_confirmado_por: Ator | null;
  endereco_manual_confirmado_em: string | null;

  // ─── Empreendimento manual override (migration 158) ────────────────────
  // The development/condomínio name for a manually registered imóvel
  // (migration 149), which has no Vista mirror row and therefore no
  // `imoveis.empreendimento` at all — without this, its contract title
  // silently omits the development name. `null` means "use the mirror".
  empreendimento_manual: string | null;
  empreendimento_manual_confirmado_por: Ator | null;
  empreendimento_manual_confirmado_em: string | null;

  updated_at: string | null;
}

/** `PUT .../endereco-manual` body — absence means "leave alone", `null`
 *  means "clear the override and fall back to the mirror" (migration 149,
 *  widened by 159 to all 7 fields). */
export interface EnderecoManualPatch {
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  uf?: string | null;
  cep?: string | null;
}

/** One row of `GET .../endereco-manual/historico` — an append-only log of
 *  every field-level override (migration 149, widened by 159). */
export interface EnderecoManualHistoricoItem {
  campo: "logradouro" | "numero" | "complemento" | "bairro" | "cidade" | "uf" | "cep";
  valor_anterior: string | null;
  valor_novo: string | null;
  alterado_por: Ator | null;
  alterado_em: string;
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
  empreendimento_manual?: string | null;
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

  // ─── Structured read (migration 118) ───────────────────────────────────
  // A SECOND, independent read of the same PDF: the certidão's own número,
  // dates and resultado — a different question from the número de matrícula
  // above, which is why it has its own fields and its own confirmation.
  // Which of these a document carries depends on its `tipo_documento`
  // (`CAMPOS_POR_TIPO` in `useImovelContrato.ts`); the rest stay null.
  numero?: string | null;
  /** The date printed ON the certidão — the office's 30-day rule runs from
   *  here, never from `created_at`. */
  emitida_em?: string | null;
  validade_ate?: string | null;
  resultado?: string | null;
  inscricao_imobiliaria?: string | null;
  /** `'ia'` (the read) | `'manual'` (an operator confirmed/corrected it). */
  origem?: string | null;
  confirmado_por?: Ator | null;
  confirmado_em?: string | null;
}

export interface DocumentoUrlResponse {
  url: string;
  expires_at: string;
}

interface ItemsEnvelope<T> {
  items: T[];
  total: number;
}

/**
 * The document types this surface offers, in the order they are asked for.
 * Mirrors `documentos_service.TIPOS_DOCUMENTO`; `cnd_iptu`/`cnd_condominio`
 * joined in migration 118 — the contract's imóvel CND group.
 */
export const TIPOS_DOCUMENTO = [
  { value: "matricula", label: "Matrícula" },
  { value: "guia_iptu", label: "Guia de IPTU" },
  { value: "cnd_iptu", label: "CND de IPTU" },
  { value: "cnd_condominio", label: "CND de condomínio" },
] as const;

// ─── Query keys ─────────────────────────────────────────────────────────────

const FAMILY_KEY = (codigo: string) => ["sw", "imovel-dados", codigo] as const;
const DADOS_KEY = (codigo: string) => [...FAMILY_KEY(codigo), "dados"] as const;
const DOCUMENTOS_KEY = (codigo: string) =>
  [...FAMILY_KEY(codigo), "documentos"] as const;
const ENDERECO_MANUAL_HISTORICO_KEY = (codigo: string) =>
  [...FAMILY_KEY(codigo), "endereco-manual-historico"] as const;

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

function extracaoEmAndamento(status: string | null | undefined): boolean {
  return status === "pendente" || status === "processando";
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
      const trabalhando = docs.some((d) => extracaoEmAndamento(d.extracao_status));
      return trabalhando ? 3000 : false;
    },
  });
}

/**
 * P1/883 live bug (2026-09-24): `useImovelDocumentos` above already polled
 * a document's OWN `extracao_status`/`extracao_matricula` (so
 * `ImovelDocumentosCard`'s "Lendo…" spinner did update) — but nothing ever
 * invalidated `useImovelDados` (`DADOS_KEY`), the SEPARATE query that holds
 * `numero_matricula`/`prefeitura_cadastro_imobiliario`/título/ônus, which the
 * full transcription's D1 apply (`preenchimento_service.preencher_imovel`,
 * a DIFFERENT detached background task than the document's own vision-only
 * number read) fills on its own schedule. So "Dados do Imóvel" kept showing
 * the pre-extraction snapshot until a hard reload, same shape
 * `useCardHub.useExtracaoPollingInvalidation` already fixed for a cliente's
 * checklist/qualificação (b9ff02e15) — this is that pattern's imóvel sibling.
 *
 * Mount once per imóvel page (`ImovelDetalhes`) alongside
 * `useImovelDocumentos(codigo)` — same query key, so this shares that
 * hook's cache/fetch rather than doubling the request. The FIRST refetch
 * that flips any document from pending to terminal invalidates the whole
 * `imovel-dados` family (`dados`/`documentos`/`endereco-manual-historico`)
 * and the `imovel-contrato` family (título/onus/endereco-registro/certidões
 * — fed by the SAME `preencher_imovel` call). Returns nothing: callers keep
 * using `useImovelDocumentos`'s own result for render data; this hook is
 * mounted purely for the polling + invalidation side effect.
 */
export function useImovelExtracaoPollingInvalidation(codigo: string | null): void {
  const qc = useQueryClient();
  const prevStatusRef = useRef<Map<string, string | null | undefined>>(new Map());
  const query = useImovelDocumentos(codigo);

  useEffect(() => {
    if (!codigo || !query.data) return;
    const prev = prevStatusRef.current;
    const proximo = new Map(query.data.map((d) => [d.id, d.extracao_status] as const));
    const transicionou = query.data.some((d) => {
      const antes = prev.get(d.id);
      // `undefined` = this document's first appearance in the map (the
      // panel just mounted, or it was just uploaded) — never itself a
      // transition; only a PREVIOUSLY-seen pending status turning terminal
      // counts, same rule `useCardHub`'s sibling hook applies.
      return antes !== undefined && extracaoEmAndamento(antes) && !extracaoEmAndamento(d.extracao_status);
    });
    prevStatusRef.current = proximo;
    if (transicionou) {
      void Promise.all([
        qc.invalidateQueries({ queryKey: FAMILY_KEY(codigo) }),
        qc.invalidateQueries({ queryKey: ["sw", "imovel-contrato", codigo] }),
      ]);
    }
  }, [codigo, query.data, qc]);
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

/** `GET .../endereco-manual/historico` — the override audit trail. */
export function useEnderecoManualHistorico(codigo: string | null) {
  return useQuery({
    queryKey: ENDERECO_MANUAL_HISTORICO_KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<EnderecoManualHistoricoItem>>(
        `${base(codigo as string)}/endereco-manual/historico`,
      );
      return res?.items ?? [];
    },
    enabled: !!codigo,
  });
}

export function useEnderecoManualMutation(codigo: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: EnderecoManualPatch) =>
      api.put<ImovelDados>(`${base(codigo)}/endereco-manual`, patch),
    onSuccess: (data) => {
      qc.setQueryData(DADOS_KEY(codigo), data);
      qc.invalidateQueries({ queryKey: ENDERECO_MANUAL_HISTORICO_KEY(codigo) });
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
    // Migration 118: a CND upload changes the certidões group, and an
    // uploaded/removed matrícula moves the título/ônus reads — all of them
    // live under the `imovel-contrato` family (`useImovelContrato.ts`).
    // Invalidated here rather than in that file so ONE place knows what an
    // upload makes stale.
    qc.invalidateQueries({ queryKey: ["sw", "imovel-contrato", codigo] });
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

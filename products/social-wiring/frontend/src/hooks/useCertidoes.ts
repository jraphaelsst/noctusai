/**
 * Certidões Negativas — query/mutation hooks.
 *
 * Ported verbatim (shapes AND polling contract) from
 * `erp-imobiliario/frontend/src/hooks/useCertidoes.ts` as ERP is retired.
 * Wraps `/api/certidoes/*` on the social-wiring backend.
 *
 * The polling here IS the feature, not a nicety: a consulta fans out into ~8
 * tribunal scrapes that finish minutes apart, and the page is the only place
 * the user can see which ones landed. Three independent intervals, each of
 * which returns `false` the moment there is nothing live to watch:
 *
 *   - consultas list  → 3s while ANY consulta is pendente/processando
 *   - consulta detail → 3s while THAT consulta is pendente/processando
 *   - TJSP queue      → 15s while the queue is non-empty or cooldown is active
 *
 * `useCertidaoConsultas` carries `placeholderData: (prev) => prev` because its
 * key includes the search/status filters: without it, every keystroke in the
 * search box drops `data` to undefined and unmounts the whole list. The page
 * pairs that with `isPending && !data` for the skeleton (never `isLoading`,
 * never a bare `isFetching`) — see KB § PATTERNS/frontend/lying-loading-state.md.
 */
import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuthStore } from "@noctusai/seed/infra";
import { copyRichText } from "@noctusai/lib/clipboard";

import { api } from "@/lib/api";
import { apiUrl } from "@/lib/apiBase";
import { authenticatedFetch, triggerBlobDownload } from "@/lib/file-download";
import { readableError, type FormatRange } from "@/hooks/useMatriculas";
import type {
  ResultadoOrigem,
  ResultadoPatchInput,
  ResultadoValor,
} from "@/types/certidoesEstruturadas";

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * `na_fila` is NOT a synonym for `pendente`: TJSP rate-limits to one request
 * per 30 minutes, so a certificate can sit in an explicit queue with a visible
 * position. Collapsing it into `pendente` is what makes the page look stuck.
 */
export type CertidaoResultadoStatus = "pendente" | "processando" | "na_fila" | "sucesso" | "erro";

export interface CertidaoResultado {
  id: string;
  consulta_id: string;
  tipo: string;
  nome_display: string;
  ordem: number;
  status: CertidaoResultadoStatus;
  analise_ia?: string;
  arquivo_url?: string;
  arquivo_nome?: string;
  erro_mensagem?: string;
  created_at: string;
  /**
   * Contract automation F1 (migration 107) — structured fields + provenance,
   * present on EVERY resultado read (`select("*")` on both the per-consulta
   * detail endpoint and the per-parte endpoint below), not just the ones
   * fetched through `useResultadosPorParte`. See
   * `@/types/certidoesEstruturadas` for the value vocabularies.
   */
  numero?: string | null;
  emitida_em?: string | null; // YYYY-MM-DD
  validade_ate?: string | null; // YYYY-MM-DD
  resultado?: ResultadoValor | null;
  resultado_origem?: ResultadoOrigem | null;
  confirmado_por?: string | null;
  confirmado_em?: string | null;
  /** Only populated by `GET /partes/{id}/resultados` — the consulta this
   * resultado's row belongs to, denormalized so the per-parte panel does not
   * need a second fetch to label its own list. `null`/absent elsewhere. */
  consulta_nome?: string | null;
  consulta_documento?: string | null;
  /** Migration 113 (ABNT formatting project, `projects/abnt-formatting-
   *  CONTRACT.md` § 4) — `GENERATED ALWAYS AS (texto_extraido IS NOT NULL)`.
   *  Gates the "Transcrição PDF" / "Copiar" actions; `false`/absent hides
   *  both (a failed transcription never surfaces as a broken button). */
  tem_transcricao?: boolean;
}

/** `GET /api/certidoes/resultados/{id}/transcricao` envelope's `data` — the
 *  "Copiar" action's source (ABNT formatting project § 4). */
export interface TranscricaoResultado {
  texto: string;
  texto_html: string;
  formatacao: FormatRange[];
}

export interface TjspFilaItem {
  id: string;
  consulta_id: string;
  posicao: number;
  nome: string;
  documento: string;
  tipo_documento: string;
  created_at: string;
}

export interface TjspFilaStatus {
  items: TjspFilaItem[];
  total_na_fila: number;
  cooldown: {
    ativo: boolean;
    ultimo_request_at?: string;
    segundos_restantes?: number;
  };
}

export interface CertidaoConsulta {
  id: string;
  tipo_documento: "cpf" | "cnpj";
  documento: string;
  nome: string;
  data_nascimento?: string;
  genero?: string;
  rg?: string;
  nome_mae?: string;
  nome_pai?: string;
  status: "pendente" | "processando" | "concluida" | "erro";
  total_certidoes: number;
  concluidas: number;
  erros: number;
  created_at: string;
  resultados?: CertidaoResultado[];
  /** Contract automation F1 (migration 107) — nullable linkage to a party of
   * an atendimento, set together by `POST /consultas/{id}/vincular-parte`.
   * `null` for ad-hoc consultas not tied to any deal. */
  cliente_id?: string | null;
  atendimento_parte_id?: string | null;
}

export interface ConsultaCreateData {
  tipo_documento: "cpf" | "cnpj";
  documento: string;
  nome: string;
  data_nascimento?: string;
  genero?: string;
  rg?: string;
  nome_mae?: string;
  nome_pai?: string;
}

export interface FiltrosConsultas {
  busca?: string;
  status?: string;
}

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useCertidaoConsultas(filtros?: FiltrosConsultas) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["certidao-consultas", filtros],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (filtros?.busca) params.busca = filtros.busca;
      if (filtros?.status && filtros.status !== "todos") params.status = filtros.status;
      const result = await api.get("/api/certidoes/consultas", params);
      return (result.data || []) as CertidaoConsulta[];
    },
    enabled: !!user,
    staleTime: 30 * 1000, // 30s — data changes during processing
    refetchInterval: (query) => {
      const data = query.state.data as CertidaoConsulta[] | undefined;
      if (data?.some((c) => c.status === "pendente" || c.status === "processando")) {
        return 3000; // Poll every 3s for real-time progress updates
      }
      return false;
    },
    // Key includes the filters — without this, typing in the search box
    // unmounts the table between keystrokes.
    placeholderData: (prev) => prev,
  });
}

export function useCertidaoConsulta(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["certidao-consulta", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/certidoes/consultas/${id}`);
      return result.data as CertidaoConsulta;
    },
    enabled: !!user && !!id,
    staleTime: 5 * 1000, // 5s — poll frequently during processing
    refetchInterval: (query) => {
      const data = query.state.data as CertidaoConsulta | null | undefined;
      if (data && (data.status === "pendente" || data.status === "processando")) {
        return 3000; // Poll every 3s for real-time progress updates
      }
      return false;
    },
  });
}

export function useTjspFila() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["tjsp-fila"],
    queryFn: async () => {
      const result = await api.get("/api/certidoes/fila-tjsp");
      return result.data as TjspFilaStatus;
    },
    enabled: !!user,
    staleTime: 10 * 1000,
    refetchInterval: (query) => {
      const data = query.state.data as TjspFilaStatus | undefined;
      if (data && (data.total_na_fila > 0 || data.cooldown.ativo)) {
        return 15000; // Poll every 15s while queue is active
      }
      return false;
    },
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useCreateConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ConsultaCreateData) => {
      const result = await api.post("/api/certidoes/consultas", data);
      return result.data as CertidaoConsulta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      toast.success("Consulta de certidões iniciada!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar consulta", { description: error.message });
    },
  });
}

export function useReprocessarConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/api/certidoes/consultas/${id}/reprocessar`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      queryClient.invalidateQueries({ queryKey: ["certidao-consulta"] });
      toast.success("Reprocessamento iniciado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao reprocessar", { description: error.message });
    },
  });
}

export function useDeleteConsulta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/certidoes/consultas/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      toast.success("Consulta excluída com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir consulta", { description: error.message });
    },
  });
}

export function useCancelarProcessamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (consultaId: string) => {
      const result = await api.post(`/api/certidoes/consultas/${consultaId}/cancelar`);
      return result.data as { cancelados: number };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      queryClient.invalidateQueries({ queryKey: ["certidao-consulta"] });
      queryClient.invalidateQueries({ queryKey: ["tjsp-fila"] });
      toast.success(`${data.cancelados} certidão(ões) cancelada(s)`);
    },
    onError: (error: Error) => {
      toast.error("Erro ao cancelar processamento", { description: error.message });
    },
  });
}

// ─── Contract automation F1 — per-parte structured certidões (migration 107) ─
//
// `CertidoesPartePanel`'s data layer: every certidão result linked to one
// party of an atendimento, plus the three actions that mutate a resultado
// from that panel (link a consulta, confirm/correct, mint a viewing URL).
// The existing upload endpoint is reused as-is — see `useUploadResultadoManual`.

export function useResultadosPorParte(atendimentoParteId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["certidao-resultados-parte", atendimentoParteId],
    queryFn: async () => {
      const result = await api.get(`/api/certidoes/partes/${atendimentoParteId}/resultados`);
      return (result.data || []) as CertidaoResultado[];
    },
    enabled: !!user && !!atendimentoParteId,
    staleTime: 5 * 1000,
    // Mirrors `useCertidaoConsulta`'s own polling: a resultado fanned out by
    // `vincular_parte` (or still being scraped by the original consulta) can
    // land after this panel is already open.
    refetchInterval: (query) => {
      const data = query.state.data as CertidaoResultado[] | undefined;
      if (data?.some((r) => r.status === "pendente" || r.status === "processando")) {
        return 3000;
      }
      return false;
    },
    placeholderData: (prev) => prev,
  });
}

export function useVincularParte() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      consultaId,
      atendimentoParteId,
    }: {
      consultaId: string;
      atendimentoParteId: string;
    }) => {
      const result = await api.post(`/api/certidoes/consultas/${consultaId}/vincular-parte`, {
        atendimento_parte_id: atendimentoParteId,
      });
      return result.data as CertidaoConsulta;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["certidao-resultados-parte", variables.atendimentoParteId],
      });
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      toast.success("Consulta vinculada à parte!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao vincular consulta", { description: error.message });
    },
  });
}

/** `atendimentoParteId` scopes cache invalidation only — the mutation itself
 * targets a resultado id, not a parte. */
export function useConfirmarResultado(atendimentoParteId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      resultadoId,
      patch,
    }: {
      resultadoId: string;
      patch: ResultadoPatchInput;
    }) => {
      const result = await api.patch(`/api/certidoes/resultados/${resultadoId}`, patch);
      return result.data as CertidaoResultado;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["certidao-resultados-parte", atendimentoParteId],
      });
      toast.success("Resultado confirmado!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao confirmar resultado", { description: error.message });
    },
  });
}

/** Same `/resultados/{id}/upload` endpoint `pages/Certidoes.tsx` calls
 * directly — wrapped here so the per-parte panel gets the same PDF-only
 * guard + toast + cache-invalidation as a mutation, instead of a second
 * hand-rolled `handleFileSelected`. */
export function useUploadResultadoManual(atendimentoParteId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ resultadoId, file }: { resultadoId: string; file: File }) => {
      if (file.type !== "application/pdf") {
        throw new Error("Apenas arquivos PDF são aceitos.");
      }
      const formData = new FormData();
      formData.append("file", file);
      // `api.upload`, not a hand-rolled multipart fetch — same seam
      // `pages/Certidoes.tsx::handleFileSelected` uses, for the same reason.
      await api.upload(`/api/certidoes/resultados/${resultadoId}/upload`, formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["certidao-resultados-parte", atendimentoParteId],
      });
      queryClient.invalidateQueries({ queryKey: ["certidao-consulta"] });
      queryClient.invalidateQueries({ queryKey: ["certidao-consultas"] });
      toast.success("Certidão enviada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao enviar certidão", { description: error.message });
    },
  });
}

/** A short-TTL signed URL for one resultado's file — action-triggered
 * (view/download click), not cached, hence a mutation rather than a query. */
export function useMintResultadoUrl() {
  return useMutation({
    mutationFn: async ({
      resultadoId,
      intent,
    }: {
      resultadoId: string;
      intent: "view" | "download";
    }) => {
      const result = await api.get(`/api/certidoes/resultados/${resultadoId}/url`, { intent });
      return result.data as { url: string; expires_at: string | null };
    },
    onError: (error: Error) => {
      toast.error("Erro ao obter arquivo", { description: error.message });
    },
  });
}

// ─── ABNT formatting project — transcript retrieval (migration 113) ────────
//
// `projects/abnt-formatting-CONTRACT.md` § 4 + § 6. Both actions are gated
// on `resultado.tem_transcricao === true` by the callers (`pages/Certidoes.tsx`
// and `CertidoesPartePanel`) — shared here so neither hand-rolls the fetch
// or the copy-with-fallback logic a second time.

/** GET `/resultados/{id}/transcricao` — the "Copiar" action's JSON source.
 *  Action-triggered (not cached), same shape as `useMintResultadoUrl`. */
export function useTranscricaoResultado() {
  return useMutation({
    mutationFn: async (resultadoId: string) => {
      const result = await api.get(`/api/certidoes/resultados/${resultadoId}/transcricao`);
      return result.data as TranscricaoResultado;
    },
    onError: (error: Error) => {
      toast.error("Erro ao obter transcrição", { description: readableError(error) });
    },
  });
}

/** GET `/resultados/{id}/transcricao/pdf` — raw fetch (binary), not the JSON
 *  `api` client, mirroring `useMatriculas.ts`'s own PDF download. `filename`
 *  is the fallback used only when the server's `Content-Disposition` is
 *  missing or unparseable. */
export function useDownloadTranscricaoPdf() {
  return useMutation({
    mutationFn: async ({ resultadoId, filename }: { resultadoId: string; filename: string }) => {
      const url = apiUrl(`/api/certidoes/resultados/${resultadoId}/transcricao/pdf`);
      const resp = await authenticatedFetch(url);
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        throw new Error(body?.detail || "Erro ao baixar transcrição");
      }
      const disposition = resp.headers.get("Content-Disposition") || "";
      const match = /filename="?([^"]+)"?/.exec(disposition);
      const blob = await resp.blob();
      triggerBlobDownload(blob, match?.[1] || filename);
    },
    onError: (error: Error) => {
      toast.error(error.message || "Erro ao baixar transcrição");
    },
  });
}

/**
 * Composes `useTranscricaoResultado` + the seed `copyRichText` into the
 * "Copiar" action shared by `pages/Certidoes.tsx` and `CertidoesPartePanel`
 * — both render a transcribed resultado's copy button and neither should
 * hand-roll the fetch-then-clipboard sequence a second time.
 *
 * `copyRichText`'s `{ rich: false }` fallback (browser lacks `ClipboardItem`)
 * is surfaced via a distinct toast copy — never treated as equivalent to a
 * rich copy, per the helper's own contract.
 */
export function useCopiarTranscricao() {
  const transcricao = useTranscricaoResultado();

  const copiar = useCallback(
    (resultadoId: string, onCopied?: () => void) => {
      transcricao.mutate(resultadoId, {
        onSuccess: async (data) => {
          try {
            const result = await copyRichText(data.texto_html, data.texto);
            toast.success(result.rich ? "Texto copiado!" : "Texto copiado (sem formatação).");
            onCopied?.();
          } catch {
            toast.error("Não foi possível copiar o texto.");
          }
        },
      });
    },
    [transcricao],
  );

  return {
    copiar,
    isPending: transcricao.isPending,
    /** The resultado id currently being copied, for a per-row spinner. */
    activeId: transcricao.variables,
  };
}

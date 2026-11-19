/**
 * Criação pipeline hooks (criacao-pipeline-contract.md §1, §3, §7 S11).
 *
 * Contract-first: the backend slices (S5 stage model/approvals, S6 worker/progress/quota, S1 seed pipeline
 * stream) land in parallel, so every route below is a typed seam named after its contract entry:
 *
 * - `POST   {ESTEIRA_BASE}/posts/{id}/aprovacoes   {alvo, decisao, motivo?}` -> `PostDetalhe` (approval organ).
 * - `GET    {ESTEIRA_BASE}/posts/{id}/criacao/progress` (SSE `JobProgress`, scope
 *   `job_progress_scope(org, "{post}:{rodada}")`) -> `useCriacaoProgresso`.
 * - `GET    {ESTEIRA_BASE}/stream` (SSE `pipeline.card_moved` / `pipeline.card_state`) -> `useEsteiraStream`.
 * - `GET/PUT {CRIACAO_BASE}/cota` -> monthly vendor-cost cap (default US$15, org-admin editable).
 *
 * Loading rule (lying-loading-state.md): `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useJobProgress, useRealtimeStream, type RealtimeMessage } from "@noctusai/lib";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api, getAuthToken } from "@noctusai/seed/infra";
import { useCallback, useMemo } from "react";

import { ESTEIRA_KEY, ESTEIRA_PIPELINE_KEY } from "@/lib/esteiraKeys";
import type {
  AlvoAprovacao,
  CotaCriacao,
  CriacaoEstado,
  CriacaoProgresso,
  DecisaoAprovacao,
  PostDetalhe,
} from "@/types/esteira";
import { ESTEIRA_BASE, esteiraKeys, POST_SETTLE, postTargets } from "./useEsteira";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

export const CRIACAO_BASE = "/api/media-creation/criacao";
export const COTA_PADRAO_USD = 15;

export const criacaoKeys = {
  cota: [...ESTEIRA_KEY, "criacao", "cota"] as const,
  progresso: (postId: string | null) => [...ESTEIRA_KEY, "criacao", "progresso", postId] as const,
};

// ─── Sub-state ──────────────────────────────────────────────────────────────

/** Sub-states in which the pipeline is working by itself (a live status line is worth showing). */
const ESTADOS_EM_ANDAMENTO: ReadonlySet<CriacaoEstado> = new Set(["na_fila", "gerando", "refinando"]);

export const emAndamentoCriacao = (e: CriacaoEstado | null | undefined): boolean =>
  !!e && ESTADOS_EM_ANDAMENTO.has(e);

/** pt-BR sentence for a sub-state, used when no live frame is available (reload, stream down). */
export const ESTADO_ROTULO: Record<CriacaoEstado, string> = {
  aguardando_aprovacao: "Aguardando sua aprovação",
  refinando: "Refinando com a IA",
  aprovado: "Aprovado, entrando na fila de criação",
  na_fila: "Na fila de criação",
  gerando: "Gerando a mídia",
  aguardando_edicao: "Aguardando edição",
  aguardando_aprovacao_midia: "Mídia pronta, aguardando sua aprovação",
  midia_aprovada: "Mídia aprovada",
  midia_reprovada: "Mídia reprovada, voltando para a criação",
  falhou: "A criação falhou",
  cancelado: "Criação cancelada",
};

// ─── Live progress (per post) ───────────────────────────────────────────────

/**
 * What the agent is doing right now, pushed by the criação worker. Wraps the seed `useJobProgress`
 * (SSE first, polling the post as the fallback). Enabled only while the sub-state says the pipeline is
 * running, so an idle card opens no stream. A missing value stays `null`: never an invented percentage.
 */
export function useCriacaoProgresso(postId: string | null, estado: CriacaoEstado | null | undefined) {
  const ativo = !!postId && emAndamentoCriacao(estado);
  const { progress, mode } = useJobProgress({
    jobId: postId,
    url: postId ? `${ESTEIRA_BASE}/posts/${encodeURIComponent(postId)}/criacao/progress` : null,
    getAuthToken,
    readKey: esteiraKeys.post(postId),
    enabled: ativo,
  });
  const valor = useMemo<CriacaoProgresso | null>(
    () =>
      progress
        ? { passo: progress.stage, mensagem: progress.message, progresso: progress.progress, terminal: progress.terminal }
        : null,
    [progress],
  );
  return { progresso: valor, mode, ativo };
}

// ─── Board stream ───────────────────────────────────────────────────────────

export const ESTEIRA_STREAM_EVENTS = ["pipeline.card_moved", "pipeline.card_state"] as const;

/**
 * Board push: the system moves cards by itself (criação -> edição -> aprovação final), so the board
 * re-reads on `pipeline.card_moved` / `pipeline.card_state` instead of waiting for a poll.
 *
 * NOC-REMEDIATE[pipeline-stream-seed-hook]: slice S1 ships the seed `useEsteiraStream`/pipeline-stream
 * hook on `feat/seed-pipeline-stream`; this is the typed seam over `useRealtimeStream` and retires onto
 * the seed hook once it is on dev — 2026-11-19. Fallback when the stream is down is the board's own poll.
 */
export function useEsteiraStream(options: { enabled?: boolean } = {}) {
  const qc = useQueryClient();
  const onEvent = useCallback(
    (m: RealtimeMessage) => {
      if (!(ESTEIRA_STREAM_EVENTS as readonly string[]).includes(m.event)) return;
      const cardId = typeof m.payload.card_id === "string" ? m.payload.card_id : null;
      void qc.invalidateQueries({ queryKey: [ESTEIRA_PIPELINE_KEY] });
      if (cardId) void qc.invalidateQueries({ queryKey: esteiraKeys.post(cardId) });
    },
    [qc],
  );
  return useRealtimeStream(`${ESTEIRA_BASE}/stream`, {
    getAuthToken,
    events: ESTEIRA_STREAM_EVENTS,
    enabled: options.enabled ?? true,
    onEvent,
  });
}

// ─── Approvals ──────────────────────────────────────────────────────────────

export interface AprovacaoInput {
  postId: string;
  alvo: AlvoAprovacao;
  decisao: DecisaoAprovacao;
  /** Required by the server on `reprovar` (sent back to refine with this reason). */
  motivo?: string;
}

const ERROS_APROVACAO: Record<string, string> = {
  motivo_obrigatorio: "Explique o que precisa mudar para devolver ao refinamento.",
  cota_excedida: "O limite mensal de custo da criação foi atingido. Ajuste o limite para continuar.",
  estado_invalido: "Este item não está mais aguardando aprovação. Atualize o card.",
};

/** pt-BR message for a refused approval (never silent). */
export function mensagemAprovacao(e: unknown, fallback = "Não foi possível registrar a decisão."): string {
  const codigo = (e as { code?: string; body?: { code?: string } } | null)?.code ?? (e as any)?.body?.code;
  return (codigo && ERROS_APROVACAO[codigo]) || fallback;
}

/**
 * Approve / reject the headline, the roteiro or the final media. The server answer (the post with its new
 * sub-state) is committed into the post detail and every cached board card; the board and the Geração
 * families settle in the background (approval can move the card).
 */
export function useAprovarEtapa() {
  return useCacheWriteMutation<PostDetalhe, AprovacaoInput>({
    mutationFn: async ({ postId, alvo, decisao, motivo }) =>
      unwrap(
        await api.post<Envelope<PostDetalhe>>(`${ESTEIRA_BASE}/posts/${encodeURIComponent(postId)}/aprovacoes`, {
          alvo,
          decisao,
          ...(motivo ? { motivo } : {}),
        }),
      ),
    targets: (v) => postTargets(v.postId),
    invalidate: POST_SETTLE,
  });
}

// ─── Monthly cost cap ───────────────────────────────────────────────────────

export function useCotaCriacao() {
  const query = useQuery({
    queryKey: criacaoKeys.cota,
    queryFn: async () => unwrap(await api.get<Envelope<CotaCriacao>>(`${CRIACAO_BASE}/cota`)),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useAtualizarCota() {
  return useCacheWriteMutation<CotaCriacao, { limite_usd_mes: number }>({
    mutationFn: async (body) => unwrap(await api.put<Envelope<CotaCriacao>>(`${CRIACAO_BASE}/cota`, body)),
    targets: () => [{ queryKey: criacaoKeys.cota, commit: (_old: CotaCriacao | undefined, saved: CotaCriacao) => saved }],
    invalidate: [criacaoKeys.cota],
  });
}

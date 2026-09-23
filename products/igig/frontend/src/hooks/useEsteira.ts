/**
 * Esteira de Produção hooks — Módulo 4, on the seed pipeline (roadmap R3).
 *
 * Backend mirror: `app/routers/esteira_router.py` + `app/services/esteira_quadro.py`.
 *
 * Two audiences in one file, deliberately separated below:
 *   - the agency's team (authenticated) — the board, tarefa CRUD, timesheet, link
 *   - the agency's CLIENT (public, token-authenticated) — the approval portal
 *
 * THE BOARD is the seed `createPipelineHooks` over `/api/esteira/board`: the
 * stages are the org's own editable rows (migration 017), so the column list,
 * the optimistic drag and its rollback all come from the seed — this file only
 * declares the descriptor. The legacy `/quadro` + `/mover` pair is gone
 * server-side, and so is its hand-rolled optimistic mutation here.
 *
 * `loading` is `isPending && !data` — first load only, never `isLoading` and
 * never `|| isFetching` (`KB § PATTERNS/frontend/lying-loading-state.md`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createPipelineHooks } from "@noctusai/lib/components";

import { api } from "@/lib/api";

// ─── Types (mirror backend app/schemas/esteira.py + esteira_quadro.quadro) ──
/** A tarefa as the board serves it — the row plus what a phone needs to read it. */
export interface TarefaCard {
  id: string;
  org_id: string;
  pauta_id: string;
  cliente_id: string | null;
  titulo: string;
  etapa_id: string;
  kanban_pos?: number | string | null;
  responsavel_id: string | null;
  prazo: string | null;
  refacoes: number;
  observacao_cliente: string | null;
  created_at: string | null;
  updated_at: string | null;
  pauta: {
    id: string;
    titulo: string;
    formato: string | null;
    data_publicacao: string | null;
  } | null;
  cliente: { id: string; nome: string } | null;
  responsavel: { id: string; nome: string } | null;
}

export interface Apontamento {
  id: string;
  org_id: string;
  tarefa_id: string;
  usuario_id: string;
  profissional_id: string | null;
  iniciado_em: string;
  encerrado_em: string | null;
  minutos: number;
}

export interface LinkAprovacao {
  id: string;
  tarefa_id: string;
  token: string;
  expira_em: string | null;
  decidido_em: string | null;
  decisao: string | null;
}

export const ESTEIRA_QUERY_KEY = ["igig", "esteira"] as const;
/** Root key of the seed board query (`[ESTEIRA_BOARD_KEY, filtros]`). */
export const ESTEIRA_BOARD_KEY = "igig-esteira-board";

/**
 * The esteira board. A tarefa has no money, so `getCardValue` is 0 and the
 * column total stays empty (the board renders `formatValue` → "").
 */
export const esteiraPipeline = createPipelineHooks<TarefaCard>(
  {
    queryKey: ESTEIRA_BOARD_KEY,
    boardEndpoint: "/api/esteira/board",
    stagesEndpoint: "/api/esteira/stages",
    moveEndpoint: "/api/esteira/tarefas",
    getCardId: (t) => t.id,
    getCardValue: () => 0,
    entityLabel: "tarefa",
  },
  api,
);

/** After any tarefa write: the board (every filter variant) and the side queries. */
function useInvalidarEsteira() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: [ESTEIRA_BOARD_KEY] });
    void qc.invalidateQueries({ queryKey: ESTEIRA_QUERY_KEY });
  };
}

// ─── Agency-side (authenticated) ───────────────────────────────────────
/**
 * Create a tarefa. It lands in the board's FIRST stage (server rule) and takes
 * its cliente from the pauta — so the caller supplies a pauta, never a cliente.
 */
export function useCriarTarefa() {
  const invalidar = useInvalidarEsteira();
  return useMutation({
    mutationFn: (payload: {
      pauta_id: string;
      titulo: string;
      responsavel_id?: string | null;
      prazo?: string | null;
    }) => api.post<TarefaCard>("/api/esteira/tarefas", payload),
    onSuccess: invalidar,
  });
}

/** `DELETE /api/esteira/tarefas/{id}` → 204. Apontamentos + links cascade. */
export function useExcluirTarefa() {
  const invalidar = useInvalidarEsteira();
  return useMutation({
    mutationFn: (tarefaId: string) => api.delete<null>(`/api/esteira/tarefas/${tarefaId}`),
    onSuccess: invalidar,
  });
}

/**
 * The timesheet of one tarefa, plus what the timer button needs.
 *
 * `emAndamento` is the CALLER's open segment — the server runs the timer as the
 * authenticated user (no `usuario_id` in the body, smoke finding 3), so "is my
 * timer running here" is the only question the play/pause button can ask.
 * Derived here, once, rather than in every consumer.
 */
export function useApontamentos(tarefaId: string | null, usuarioId: string | null) {
  const query = useQuery({
    queryKey: [...ESTEIRA_QUERY_KEY, "apontamentos", tarefaId],
    queryFn: () => api.get<Apontamento[]>(`/api/esteira/tarefas/${tarefaId}/apontamentos`),
    enabled: Boolean(tarefaId),
  });
  const apontamentos = query.data ?? [];
  return {
    ...query,
    apontamentos,
    emAndamento:
      apontamentos.find((a) => a.encerrado_em === null && a.usuario_id === usuarioId) ?? null,
    minutosTotais: apontamentos.reduce((soma, a) => soma + (a.minutos || 0), 0),
    loading: query.isPending && !query.data,
    refreshing: query.isFetching && !!query.data,
  };
}

/** Play — no body: the server times the AUTHENTICATED caller. */
export function useIniciarTimer() {
  const invalidar = useInvalidarEsteira();
  return useMutation({
    mutationFn: (tarefaId: string) =>
      api.post<Apontamento>(`/api/esteira/tarefas/${tarefaId}/timer/iniciar`),
    onSuccess: invalidar,
  });
}

/** Pause the caller's running segment on this tarefa. */
export function useEncerrarTimer() {
  const invalidar = useInvalidarEsteira();
  return useMutation({
    mutationFn: (tarefaId: string) =>
      api.post<Apontamento>(`/api/esteira/tarefas/${tarefaId}/timer/encerrar`),
    onSuccess: invalidar,
  });
}

/**
 * Mint the client's approval link. Server-side this ALSO moves the tarefa into
 * the approval stage (smoke finding 4), so the board is invalidated too.
 */
export function useEmitirLinkAprovacao() {
  const invalidar = useInvalidarEsteira();
  return useMutation({
    mutationFn: (tarefaId: string) =>
      api.post<LinkAprovacao>(`/api/esteira/tarefas/${tarefaId}/link-aprovacao`, {}),
    onSuccess: invalidar,
  });
}

/** The public portal URL for a token — one definition for every copy button. */
export function urlAprovacao(token: string, origin: string = window.location.origin): string {
  return `${origin}/aprovar/${token}`;
}

// ─── Client-side (PUBLIC — token is the auth) ──────────────────────────
/** A peça as the client sees it — a URL and a type, nothing else. */
export interface PecaPublica {
  url: string | null;
  mime_type: string | null;
}

export interface AprovacaoPublica {
  titulo: string;
  /** Empty when the pauta has no asset — the portal degrades to copy-only. */
  pecas: PecaPublica[];
  copy_texto: string | null;
  direcao_video: string | null;
  formato: string | null;
  cliente_nome: string | null;
  ja_decidida: boolean;
  /** False once the agency pulled the tarefa out of approval — read-only portal. */
  aguardando_aprovacao: boolean;
}

export type Decisao = "aprovado" | "ajuste";

/**
 * Fetch the content behind an approval token.
 *
 * No auth header — the client has no noc account. `retry: false` because the
 * failure modes here (unknown, expired, spent) are all permanent 404s; retrying
 * would just delay showing the user the "link inválido" state.
 */
export function useAprovacaoPublica(token: string | undefined) {
  const query = useQuery({
    queryKey: ["igig", "aprovacao-publica", token],
    queryFn: () => api.get<AprovacaoPublica>(`/api/esteira/aprovar/${token}`),
    enabled: Boolean(token),
    retry: false,
  });
  return {
    ...query,
    aprovacao: query.data ?? null,
    loading: query.isPending && !query.data,
  };
}

export function useDecidirAprovacao(token: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ decisao, observacao }: { decisao: Decisao; observacao: string }) =>
      api.post<{ ok: boolean; decisao: Decisao }>(`/api/esteira/aprovar/${token}`, {
        decisao,
        observacao,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["igig", "aprovacao-publica", token] }),
  });
}

/**
 * Esteira de Produção hooks — Módulo 4.
 *
 * Backend mirror: `app/routers/esteira_router.py`.
 *
 * Two audiences in one file, deliberately separated below:
 *   - the agency's team (authenticated) — quadro, mover, timesheet, link
 *   - the agency's CLIENT (public, token-authenticated) — the approval portal
 *
 * `loading` is `isPending && !data` — first load only, never `isLoading`
 * and never `|| isFetching`. TanStack v5's `isLoading` is false during a
 * background refetch, so `|| isFetching` was true on EVERY refetch (not just
 * the first), and the kanban/portal below would replace their whole content
 * with a skeleton on every mutation-triggered invalidation — the collapsing
 * layout the fleet audit flagged. `check_lying_loading_state` blocks the
 * `isLoading` shape; this file must not reintroduce the `isFetching`
 * equivalent.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

// ─── Types (mirror backend app/schemas/esteira.py) ─────────────────────
export type Etapa =
  | "aguardando_roteiro"
  | "roteiro_em_producao"
  | "aguardando_design"
  | "design_em_producao"
  | "revisao_interna"
  | "aprovacao_cliente"
  | "pronto_para_agendamento"
  | "agendado";

/** Portuguese labels for the 8 kanban columns. */
export const ETAPA_LABEL: Record<Etapa, string> = {
  aguardando_roteiro: "Aguardando roteiro",
  roteiro_em_producao: "Roteiro em produção",
  aguardando_design: "Aguardando design",
  design_em_producao: "Design em produção",
  revisao_interna: "Revisão interna",
  aprovacao_cliente: "Aprovação do cliente",
  pronto_para_agendamento: "Pronto para agendamento",
  agendado: "Agendado",
};

export interface Tarefa {
  id: string;
  org_id: string;
  pauta_id: string;
  titulo: string;
  etapa: Etapa;
  responsavel_id: string | null;
  prazo: string | null;
  refacoes: number;
  observacao_cliente: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Quadro {
  /** Column order comes from the BACKEND — the sequence is a business rule. */
  etapas: Etapa[];
  colunas: Record<Etapa, Tarefa[]>;
}

export interface Apontamento {
  id: string;
  org_id: string;
  tarefa_id: string;
  usuario_id: string;
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
const QUADRO_KEY = [...ESTEIRA_QUERY_KEY, "quadro"] as const;

// ─── Agency-side (authenticated) ───────────────────────────────────────
export function useQuadro() {
  const query = useQuery({
    queryKey: QUADRO_KEY,
    queryFn: () => api.get<Quadro>("/api/esteira/quadro"),
  });

  return {
    ...query,
    quadro: query.data ?? null,
    loading: query.isPending && !query.data,
  };
}

/**
 * Move a tarefa to another etapa — optimistic. The select-driven move is
 * instant in the UI (`onMutate`); without this the card would visibly snap
 * back to its old column for a full round-trip before the refetch confirms
 * the move. `onError` restores the pre-move board from the snapshot.
 */
export function useMoverTarefa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, etapa }: { id: string; etapa: Etapa }) =>
      api.post<Tarefa>(`/api/esteira/tarefas/${id}/mover`, { etapa }),
    onMutate: async ({ id, etapa }) => {
      await qc.cancelQueries({ queryKey: QUADRO_KEY });
      const previous = qc.getQueryData<Quadro>(QUADRO_KEY);
      const origem = previous
        ? (Object.keys(previous.colunas) as Etapa[]).find((e) =>
            previous.colunas[e].some((t) => t.id === id),
          )
        : undefined;
      const tarefa = previous && origem ? previous.colunas[origem].find((t) => t.id === id) : undefined;

      if (previous && origem && tarefa) {
        qc.setQueryData<Quadro>(QUADRO_KEY, {
          ...previous,
          colunas: {
            ...previous.colunas,
            [origem]: previous.colunas[origem].filter((t) => t.id !== id),
            [etapa]: [...(previous.colunas[etapa] ?? []), { ...tarefa, etapa }],
          },
        });
      }

      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(QUADRO_KEY, context.previous);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ESTEIRA_QUERY_KEY }),
  });
}

export function useApontamentos(tarefaId: string | null) {
  const query = useQuery({
    queryKey: [...ESTEIRA_QUERY_KEY, "apontamentos", tarefaId],
    queryFn: () => api.get<Apontamento[]>(`/api/esteira/tarefas/${tarefaId}/apontamentos`),
    // Only fetch once a task is actually selected.
    enabled: Boolean(tarefaId),
  });
  return {
    ...query,
    apontamentos: query.data ?? [],
    loading: query.isPending && !query.data,
  };
}

export function useIniciarTimer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tarefaId, usuarioId }: { tarefaId: string; usuarioId: string }) =>
      api.post<Apontamento>(`/api/esteira/tarefas/${tarefaId}/timer/iniciar`, {
        usuario_id: usuarioId,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ESTEIRA_QUERY_KEY }),
  });
}

export function useEncerrarTimer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tarefaId, usuarioId }: { tarefaId: string; usuarioId: string }) =>
      api.post<Apontamento>(`/api/esteira/tarefas/${tarefaId}/timer/encerrar`, {
        usuario_id: usuarioId,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ESTEIRA_QUERY_KEY }),
  });
}

export function useEmitirLinkAprovacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tarefaId: string) =>
      api.post<LinkAprovacao>(`/api/esteira/tarefas/${tarefaId}/link-aprovacao`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ESTEIRA_QUERY_KEY }),
  });
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

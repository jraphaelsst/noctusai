/**
 * Julia › Opt-outs (owner decisions 2026-10-21). The opt-out is AGENTS' record, per org; SW only displays it and lets an
 * authorised human act on it.
 *
 *   GET  /api/julia/opt-outs?limit&cursor&lead_ref                      → {data:{items, next_cursor}}
 *   POST /api/julia/opt-outs/{evento}/notificar                         → {data: evento}      (admin)
 *   GET  /api/julia/opt-outs/conversas/{conn}/{chat}/estado             → {data: EstadoOptOut} (the composer warning)
 *   POST /api/julia/opt-outs/leads/{contato}/nao-contatar {motivo}      (admin)
 *   POST /api/julia/opt-outs/leads/{contato}/reativar {motivo}          (admin)
 *   GET  /api/julia/opt-outs/solicitacoes?status&page                   → {data:{items,total}}
 *   PATCH /api/julia/opt-outs/solicitacoes/{id} {status, motivo?}       (admin)
 *
 * Loading = two signals off `data` (never `isLoading`). The per-conversation state is keyed by the conversation (no
 * `placeholderData`): it belongs to ONE lead, so showing the previous chat's value would be a lie about the wrong lead.
 */
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";

export type TipoEvento = "opt_out" | "reativacao";
export type NotificacaoStatus = "pendente" | "enviada" | "falhou";

export interface OptOutEvento {
  id: string;
  tipo: TipoEvento;
  lead_ref: string;
  lead_nome: string | null;
  lead_telefone: string | null;
  agent_nome: string | null;
  ator_user_id: string | null;
  ator_nome: string | null;
  origem: "agente" | "operador" | "integracao" | null;
  motivo: string | null;
  mensagem_lead: string | null;
  em: string | null;
  participantes_encerrados: number;
  notificacao_status: NotificacaoStatus;
  notificacao_erro: string | null;
  notificado_em: string | null;
  /** This record is the lead's ACTIVE opt-out (null = agents could not confirm). */
  ativo: boolean | null;
}
export interface OptOutPagina { items: OptOutEvento[]; next_cursor: string | null }

export interface EstadoOptOut {
  lead_ref: string | null;
  /** False = agents could not be read: the UI must say so, never act as if there were no opt-out. */
  verificado: boolean;
  opt_out_ativo: boolean;
  opt_out_em: string | null;
  motivo: string | null;
  origem: string | null;
  evento_id: string | null;
}

export type TipoSolicitacao =
  | "confirmacao" | "acesso" | "correcao" | "eliminacao" | "portabilidade" | "revogacao_consentimento" | "oposicao"
  | "info_compartilhamento" | "outro";
export type StatusSolicitacao = "aberta" | "em_analise" | "atendida" | "negada" | "cancelada";
export type PrazoSituacao = "vencida" | "vence_em_breve" | "no_prazo" | "encerrada";

export interface Solicitacao {
  id: string;
  contato_id: string;
  chat_id: string | null;
  tipo: TipoSolicitacao;
  trecho_lead: string;
  recebida_em: string;
  prazo_em: string;
  status: StatusSolicitacao;
  decidido_por: string | null;
  decidido_em: string | null;
  motivo_decisao: string | null;
  notificacao_status: NotificacaoStatus;
  notificacao_erro: string | null;
  prazo_situacao: PrazoSituacao;
}

export const ROTULO_TIPO_SOLICITACAO: Record<TipoSolicitacao, string> = {
  confirmacao: "Confirmação de tratamento",
  acesso: "Acesso aos dados",
  correcao: "Correção de dados",
  eliminacao: "Eliminação de dados",
  portabilidade: "Portabilidade",
  revogacao_consentimento: "Revogação de consentimento",
  oposicao: "Oposição ao tratamento",
  info_compartilhamento: "Informação sobre compartilhamento",
  outro: "Outro",
};
export const ROTULO_STATUS_SOLICITACAO: Record<StatusSolicitacao, string> = {
  aberta: "Aberta", em_analise: "Em análise", atendida: "Atendida", negada: "Negada", cancelada: "Cancelada",
};

export const OPT_OUTS_KEY = ["sw", "julia", "opt-outs"] as const;
export const SOLICITACOES_KEY = ["sw", "julia", "solicitacoes-titular"] as const;
export const optOutEstadoKey = (connectionId: string | null, chatId: string | null) =>
  [...OPT_OUTS_KEY, "estado", connectionId, chatId] as const;

export function useOptOuts() {
  const q = useInfiniteQuery({
    queryKey: [...OPT_OUTS_KEY, "historico"],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const p = new URLSearchParams({ limit: "50" });
      if (pageParam) p.set("cursor", pageParam);
      return (await api.get<{ data: OptOutPagina }>(`/api/julia/opt-outs?${p}`)).data;
    },
    getNextPageParam: (ultima) => ultima.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return { ...q, items, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data && !q.isFetchingNextPage };
}

function useInvalidarOptOuts() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: OPT_OUTS_KEY });
}

export function useRenotificarOptOut() {
  const inv = useInvalidarOptOuts();
  return useMutation<unknown, unknown, { eventoId: string }>({ // noc-allow: invalidate-only — retries a notification server-side and answers nothing; the new notificacao_status is the worker's, so there is no row to write into the history pages
    mutationFn: ({ eventoId }) => api.post(`/api/julia/opt-outs/${encodeURIComponent(eventoId)}/notificar`, {}),
    onSettled: inv,
  });
}

export function useReativarLead() {
  const inv = useInvalidarOptOuts();
  return useMutation<unknown, unknown, { contatoId: string; motivo: string }>({ // noc-allow: invalidate-only — the server writes a new history event and flips the lead's opt-out state; the answer carries neither (the new event is not in the response), so there is no row to write into the history pages
    mutationFn: ({ contatoId, motivo }) => api.post(`/api/julia/opt-outs/leads/${contatoId}/reativar`, { motivo }),
    onSettled: inv,
  });
}

export function useMarcarNaoContatar() {
  const inv = useInvalidarOptOuts();
  return useMutation<unknown, unknown, { contatoId: string; motivo: string }>({ // noc-allow: invalidate-only — same as reativar: a new history event plus the lead's state, built by the server
    mutationFn: ({ contatoId, motivo }) => api.post(`/api/julia/opt-outs/leads/${contatoId}/nao-contatar`, { motivo }),
    onSettled: inv,
  });
}

/** The consent state of the lead behind ONE chat (the operator composer's warning). A failed read is `isError` → the UI warns. */
export function useOptOutEstado(connectionId: string | null, chatId: string | null) {
  return useQuery({
    queryKey: optOutEstadoKey(connectionId, chatId),
    enabled: !!connectionId && !!chatId,
    retry: false,
    queryFn: async () =>
      (await api.get<{ data: EstadoOptOut }>(
        `/api/julia/opt-outs/conversas/${connectionId}/${encodeURIComponent(chatId!)}/estado`,
      )).data,
  });
}

export function useSolicitacoes(status: StatusSolicitacao | "", page: number) {
  const q = useQuery({
    queryKey: [...SOLICITACOES_KEY, status, page],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const p = new URLSearchParams({ page: String(page) });
      if (status) p.set("status", status);
      return (await api.get<{ data: { items: Solicitacao[]; total: number } }>(`/api/julia/opt-outs/solicitacoes?${p}`)).data;
    },
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

export function useDecidirSolicitacao() {
  return useCacheWriteMutation<unknown, { id: string; status: StatusSolicitacao; motivo?: string }>({
    mutationFn: ({ id, ...body }) => api.patch(`/api/julia/opt-outs/solicitacoes/${id}`, body),
    // The decision is exactly what the operator picked; the deadline situation and decidido_* stamps are the server's.
    targets: ({ id, status, motivo }) => [
      {
        queryKey: SOLICITACOES_KEY,
        match: "prefix",
        optimistic: (old: { items: Solicitacao[]; total: number } | undefined) =>
          pageOps.patch(old, id, { status, ...(motivo !== undefined ? { motivo_decisao: motivo } : {}) }),
      },
    ],
  });
}

export function formatarDataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

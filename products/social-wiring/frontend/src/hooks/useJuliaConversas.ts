/**
 * Julia › Conversas v2 (contract wave 7).
 *
 *   GET    /api/julia/conversas?aba=todas|minhas|arquivadas&q&operacao&status_sw
 *            &atendimento&responsavel&equipe&etiqueta     (lists are comma-joined)
 *   PATCH  /api/julia/contatos/{id}   {responsavel_user_id?, arquivado?, bloqueado?, etiquetas?}
 *   GET/POST /api/julia/contatos/{id}/notas · PATCH/DELETE …/notas/{notaId}
 *   POST   /api/julia/contatos/{id}/feedback  {nota: like|dislike, comentario}
 *   GET/POST /api/julia/etiquetas · PATCH/DELETE /api/julia/etiquetas/{id}
 *   GET    /api/julia/historico/{contato_id} → {data:{contato, interacoes, mensagens}}
 *            403 sem_acesso · 404 not found
 *
 * Envelope `{data: …}`. Loading = two signals off `data`; every filter-keyed
 * query keeps `placeholderData: keepPreviousData` so a filter change never
 * unmounts the list (KB § PATTERNS/frontend/lying-loading-state.md).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";

export type Aba = "todas" | "minhas" | "arquivadas";
export type OperacaoConversa = "aluguel" | "compra" | "administracao" | "atualizacao";
export type StatusSw = "enviado_sw" | "nao_pronto";
export type StatusAtendimento = "julia" | "manual";
export const SEM_RESPONSAVEL = "sem";

export interface Etiqueta { id: string; nome: string; cor?: string | null }

/** One row of the Conversas list (`GET /api/julia/conversas`). */
export interface Conversa {
  contato_id: string;
  /** WhatsApp JID — also the thread id the seed ChatWindow messages hooks read. */
  chat_id: string;
  nome: string;
  ultima_mensagem?: string | null;
  ultima_mensagem_at?: string | null;
  direcao?: "inbound" | "outbound" | null;
  nao_lidas?: number;
  agente_pausado?: boolean;
  arquivado?: boolean;
  bloqueado?: boolean;
  responsavel_user_id?: string | null;
  responsavel_nome?: string | null;
  etiquetas?: Etiqueta[];
  operacao?: OperacaoConversa | null;
  status_sw?: StatusSw | null;
  /** Wave 13: latest credit analysis for this contato (null = none). */
  credito?: { status: string; atualizado_at: string | null } | null;
}

export interface FiltrosConversas {
  q: string;
  operacao: OperacaoConversa | null;
  statusSw: StatusSw[];
  atendimento: StatusAtendimento[];
  responsaveis: string[];
  equipes: string[];
  etiquetas: string[];
}
export const FILTROS_VAZIOS: FiltrosConversas = {
  q: "", operacao: null, statusSw: [], atendimento: [], responsaveis: [], equipes: [], etiquetas: [],
};
/** Number of active drawer filters (the search box is not one). */
export function contarFiltros(f: FiltrosConversas): number {
  return (f.operacao ? 1 : 0) + f.statusSw.length + f.atendimento.length + f.responsaveis.length
    + f.equipes.length + f.etiquetas.length;
}

export const CONVERSAS_KEY = ["sw", "julia", "conversas"] as const;
export const ETIQUETAS_KEY = ["sw", "julia", "etiquetas"] as const;
export const NOTAS_KEY = ["sw", "julia", "notas"] as const;
export const HISTORICO_KEY = ["sw", "julia", "historico"] as const;

export function queryConversas(aba: Aba, f: FiltrosConversas): string {
  const p = new URLSearchParams({ aba });
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.operacao) p.set("operacao", f.operacao);
  if (f.statusSw.length) p.set("status_sw", f.statusSw.join(","));
  if (f.atendimento.length) p.set("atendimento", f.atendimento.join(","));
  if (f.responsaveis.length) p.set("responsavel", f.responsaveis.join(","));
  if (f.equipes.length) p.set("equipe", f.equipes.join(","));
  if (f.etiquetas.length) p.set("etiqueta", f.etiquetas.join(","));
  return p.toString();
}

function itens<T>(d: T[] | { items: T[] } | undefined | null): T[] {
  return Array.isArray(d) ? d : (d?.items ?? []);
}

export function useJuliaConversas(aba: Aba, filtros: FiltrosConversas, enabled = true) {
  return useQuery({
    queryKey: [...CONVERSAS_KEY, aba, filtros] as const,
    enabled,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      itens((await api.get<{ data: Conversa[] | { items: Conversa[] } }>(
        `/api/julia/conversas?${queryConversas(aba, filtros)}`)).data),
  });
}

export interface PatchContato {
  responsavel_user_id?: string | null;
  arquivado?: boolean;
  bloqueado?: boolean;
  etiquetas?: string[];
}
export function usePatchContato() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, { id: string } & PatchContato>({
    mutationFn: ({ id, ...body }) => api.patch(`/api/julia/contatos/${id}`, body),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: CONVERSAS_KEY });
      void qc.invalidateQueries({ queryKey: HISTORICO_KEY });
    },
  });
}

export function useEtiquetas() {
  return useQuery({
    queryKey: ETIQUETAS_KEY,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      itens((await api.get<{ data: Etiqueta[] | { items: Etiqueta[] } }>("/api/julia/etiquetas")).data),
  });
}
export function useEtiquetaMutations() {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ETIQUETAS_KEY });
    void qc.invalidateQueries({ queryKey: CONVERSAS_KEY });
  };
  return {
    criar: useMutation<Etiqueta, unknown, { nome: string; cor?: string }>({
      mutationFn: async (b) => (await api.post<{ data: Etiqueta }>("/api/julia/etiquetas", b)).data,
      onSuccess: refresh,
    }),
    atualizar: useMutation<unknown, unknown, { id: string; nome?: string; cor?: string }>({
      mutationFn: ({ id, ...b }) => api.patch(`/api/julia/etiquetas/${id}`, b),
      onSuccess: refresh,
    }),
    remover: useMutation<unknown, unknown, string>({
      mutationFn: (id) => api.delete(`/api/julia/etiquetas/${id}`),
      onSuccess: refresh,
    }),
  };
}

export interface Nota {
  id: string;
  texto: string;
  autor_user_id?: string | null;
  autor_nome?: string | null;
  created_at: string;
}
export function useNotas(contatoId: string | null) {
  return useQuery({
    queryKey: [...NOTAS_KEY, contatoId] as const,
    enabled: !!contatoId,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      itens((await api.get<{ data: Nota[] | { items: Nota[] } }>(`/api/julia/contatos/${contatoId}/notas`)).data),
  });
}
export function useNotaMutations(contatoId: string | null) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: [...NOTAS_KEY, contatoId] });
  const base = `/api/julia/contatos/${contatoId}/notas`;
  return {
    criar: useMutation<unknown, unknown, { texto: string }>({
      mutationFn: (b) => api.post(base, b), onSuccess: refresh,
    }),
    editar: useMutation<unknown, unknown, { id: string; texto: string }>({
      mutationFn: ({ id, texto }) => api.patch(`${base}/${id}`, { texto }), onSuccess: refresh,
    }),
    remover: useMutation<unknown, unknown, string>({
      mutationFn: (id) => api.delete(`${base}/${id}`), onSuccess: refresh,
    }),
  };
}

export function useFeedbackJulia(contatoId: string | null) {
  return useMutation<unknown, unknown, { nota: "like" | "dislike"; comentario?: string; interacao_id?: string }>({
    mutationFn: (b) => api.post(`/api/julia/contatos/${contatoId}/feedback`, b),
  });
}

// ─── History (A7) ────────────────────────────────────────────────────────────
export interface Interacao {
  id: string;
  tipo?: string | null;
  iniciada_em?: string | null;
  canal?: string | null;
  operacao?: string | null;
  status?: string | null;
  slots?: Record<string, unknown> | null;
  resumo?: string | null;
  /** Intent flags the model raised ("quer visitar", "pediu financiamento"…). */
  intencoes?: string[] | null;
}
export interface HistoricoMensagem {
  id: string;
  direction?: "inbound" | "outbound";
  body?: string | null;
  created_at: string;
  /** System timeline events (handoff, encerrar, arquivar…) arrive with tipo="evento". */
  tipo?: "mensagem" | "evento" | null;
}
export interface ContatoHistorico {
  id: string;
  nome?: string | null;
  telefone?: string | null;
  email?: string | null;
  operacao?: string | null;
  responsavel_nome?: string | null;
  etiquetas?: Etiqueta[];
  visitas?: { id: string; inicio: string; status: string; codigo_imovel?: string | null }[];
  arquivado?: boolean;
  bloqueado?: boolean;
}
export interface Historico {
  contato: ContatoHistorico;
  interacoes: Interacao[];
  mensagens: HistoricoMensagem[];
}
export function useHistorico(contatoId: string | null) {
  return useQuery({
    queryKey: [...HISTORICO_KEY, contatoId] as const,
    enabled: !!contatoId,
    retry: false,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      (await api.get<{ data: Historico }>(`/api/julia/historico/${contatoId}`)).data,
  });
}
export function codigoHttp(err: unknown): number | null {
  const s = (err as { status?: unknown } | null)?.status;
  return typeof s === "number" ? s : null;
}

export function linkHistorico(contatoId: string): string {
  return `${window.location.origin}/julia/conversas/h/${contatoId}`;
}
export const mensagemErroConversas = mensagemErroJulia;

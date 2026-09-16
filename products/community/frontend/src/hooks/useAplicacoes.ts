/**
 * Aplicações data hooks — community-m1-contract.md
 * §Endpoints#Aplicações-(perguntas-+-submissões).
 *
 * Two of these endpoints are PUBLIC (no auth): `useFormulario` (question
 * list for the public application form) and `useSubmitAplicacao` (the form
 * submission). The seed `api` client sends the request whether or not a
 * session exists (`getAuthToken` returning `null` omits the Authorization
 * header rather than failing) — so these hooks work unchanged from
 * `/inscrever`, which renders outside the authenticated app shell.
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Membro } from "@/hooks/useMembros";

export type PerguntaTipo = "texto" | "texto_longo" | "escolha_unica" | "escolha_multipla" | "booleano";
export type AplicacaoStatus = "pendente" | "aprovada" | "rejeitada";

export interface Pergunta {
  id: string;
  pergunta: string;
  tipo: PerguntaTipo;
  opcoes: string[];
  obrigatoria: boolean;
  ordem: number;
  ativa: boolean;
}

export interface PerguntaListResponse {
  items: Pergunta[];
  total: number;
}

export interface Aplicacao {
  id: string;
  nome: string;
  email: string;
  telefone: string | null;
  /** Keyed by `pergunta_id` — the FE resolves labels from `usePerguntas()`. */
  respostas: Record<string, unknown>;
  status: AplicacaoStatus;
  motivo: string | null;
  revisado_em: string | null;
  membro_id: string | null;
  created_at: string;
}

export interface AplicacoesResumo {
  pendente: number;
  aprovada: number;
  rejeitada: number;
}

export interface AplicacaoListResponse {
  items: Aplicacao[];
  total: number;
  resumo: AplicacoesResumo;
}

export interface AplicacoesParams {
  status?: AplicacaoStatus;
  page?: number;
  page_size?: number;
}

export interface SubmitAplicacaoInput {
  nome: string;
  email: string;
  telefone?: string | null;
  respostas: Record<string, unknown>;
}

export interface SubmitAplicacaoResponse {
  id: string;
  status: "pendente";
}

export interface AprovarAplicacaoInput {
  plano_id?: string | null;
  /** Only meaningful with a `plano_id` — activates the created/existing
   * membro immediately instead of leaving it `pendente`. */
  ativar?: boolean;
}

export interface AprovarAplicacaoResponse {
  aplicacao: Aplicacao;
  membro: Membro;
}

const aplicacoesKeys = {
  all: ["aplicacoes"] as const,
  list: (params?: AplicacoesParams) => ["aplicacoes", "list", params ?? {}] as const,
};

const perguntasKeys = {
  all: ["aplicacao-perguntas"] as const,
};

/** Authenticated — every question, including inactive (for the manager's editor). */
export function usePerguntas() {
  return useQuery({
    queryKey: perguntasKeys.all,
    queryFn: () => api.get<PerguntaListResponse>("/api/aplicacoes/perguntas"),
    placeholderData: keepPreviousData,
  });
}

/** PUBLIC — only `ativa=true`, ordered by `ordem`. Powers `/inscrever`. */
export function useFormulario() {
  return useQuery({
    queryKey: ["aplicacoes-formulario"],
    queryFn: () => api.get<PerguntaListResponse>("/api/aplicacoes/formulario"),
  });
}

export function useAplicacoes(params?: AplicacoesParams) {
  return useQuery({
    queryKey: aplicacoesKeys.list(params),
    queryFn: () => api.get<AplicacaoListResponse>("/api/aplicacoes", params),
    placeholderData: keepPreviousData,
  });
}

/** PUBLIC — the form's submission. Rate-limited server-side. */
export function useSubmitAplicacao() {
  return useMutation({
    mutationFn: (data: SubmitAplicacaoInput) =>
      api.post<SubmitAplicacaoResponse>("/api/aplicacoes", data),
  });
}

export function useAprovarAplicacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & AprovarAplicacaoInput) =>
      api.post<AprovarAplicacaoResponse>(`/api/aplicacoes/${id}/aprovar`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aplicacoesKeys.all });
      qc.invalidateQueries({ queryKey: ["membros"] });
    },
  });
}

export function useRejeitarAplicacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) =>
      api.post<Aplicacao>(`/api/aplicacoes/${id}/rejeitar`, { motivo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: aplicacoesKeys.all }),
  });
}

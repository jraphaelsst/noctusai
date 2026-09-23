/**
 * Automações v1 — the rules the engine runs on stage entry / SLA (wave-2
 * contract, Slice E2; roadmap R11). Backend mirror: `app/routers/automacao_router.py`,
 * engine `app/services/automacoes.py`.
 *
 *   GET    /api/automacoes?pipeline=&stage_id=        → {data: Automacao[]}
 *   POST   /api/automacoes                             (org admins) → 201 {data}
 *   PATCH  /api/automacoes/{id}                        (org admins; `pipeline` is fixed)
 *   DELETE /api/automacoes/{id}                        (org admins) → 204
 *   GET    /api/automacoes/execucoes?limit=&automacao_id=  → {data: Execucao[]}
 *
 * `acao.params` is validated PER TIPO server-side (extra keys refused → 422),
 * so the form sends exactly the keys of `PARAMS_POR_TIPO` in
 * `app/schemas/automacoes.py` — see `AcaoParams` below.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, cleanParams, unwrapData } from "@/lib/api";

export type PipelineAutomacao = "comercial" | "esteira";
export type Gatilho = "entrada_etapa" | "sla";
export type TipoAcao =
  | "criar_checklist"
  | "definir_responsavel"
  | "criar_tarefa"
  | "notificar"
  | "enviar_email"
  | "enviar_whatsapp";

/** The per-tipo params — mirror of `app/schemas/automacoes.py` `_*Params`. */
export interface AcaoParams {
  criar_checklist: { titulo: string; itens: string[] };
  definir_responsavel: { profissional_id: string };
  criar_tarefa: { titulo: string; prazo_dias?: number | null; responsavel_id?: string | null };
  notificar: { titulo?: string | null; mensagem?: string | null; usuario_ids: string[] };
  enviar_email: { assunto: string; mensagem: string; para?: string | null };
  enviar_whatsapp: { mensagem: string; para?: string | null };
}

export type Acao = { [T in TipoAcao]: { tipo: T; params: AcaoParams[T] } }[TipoAcao];

export interface Automacao {
  id: string;
  pipeline: PipelineAutomacao;
  stage_id: string;
  gatilho: Gatilho;
  sla_horas: number | null;
  acao: Acao;
  ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface AutomacaoInput {
  pipeline: PipelineAutomacao;
  stage_id: string;
  gatilho: Gatilho;
  sla_horas?: number | null;
  acao: Acao;
  ativo?: boolean;
}

export type AutomacaoPatch = Partial<Omit<AutomacaoInput, "pipeline">>;

export type ExecucaoStatus = "executando" | "sucesso" | "erro" | "ignorada";

export interface Execucao {
  id: string;
  automacao_id: string;
  entidade_id: string;
  status: ExecucaoStatus;
  detalhe: string | null;
  executado_em: string;
  automacao: { id: string; pipeline: PipelineAutomacao; stage_id: string; gatilho: Gatilho; tipo: TipoAcao } | null;
}

export const TIPO_ACAO_LABEL: Record<TipoAcao, string> = {
  criar_checklist: "Criar checklist",
  definir_responsavel: "Definir responsável",
  criar_tarefa: "Criar tarefa",
  notificar: "Notificar",
  enviar_email: "Enviar e-mail",
  enviar_whatsapp: "Enviar WhatsApp",
};

/** `criar_checklist` writes to the negócio CARD HUB — the Esteira has none
 * (the router refuses it with 422 `acao_incompativel`). */
export const TIPOS_POR_PIPELINE: Record<PipelineAutomacao, TipoAcao[]> = {
  comercial: ["criar_checklist", "definir_responsavel", "criar_tarefa", "notificar", "enviar_email", "enviar_whatsapp"],
  esteira: ["definir_responsavel", "criar_tarefa", "notificar", "enviar_email", "enviar_whatsapp"],
};

export const GATILHO_LABEL: Record<Gatilho, string> = {
  entrada_etapa: "Ao entrar na etapa",
  sla: "SLA estourado",
};

export const EXECUCAO_STATUS_LABEL: Record<ExecucaoStatus, string> = {
  executando: "Executando",
  sucesso: "Sucesso",
  erro: "Erro",
  ignorada: "Ignorada",
};

export const AUTOMACOES_QUERY_KEY = ["igig", "automacoes"] as const;

export function useAutomacoes(filtros: { pipeline?: PipelineAutomacao } = {}) {
  const params = cleanParams({ ...filtros });
  const query = useQuery({
    queryKey: [...AUTOMACOES_QUERY_KEY, "lista", params],
    queryFn: () => api.get("/api/automacoes", params).then(unwrapData<Automacao[]>),
    placeholderData: (prev) => prev,
  });
  const data = query.data;
  return {
    ...query,
    automacoes: data ?? [],
    showSkeleton: query.isPending && !data,
    isRefreshing: query.isFetching && !!data,
  };
}

export function useExecucoes(limit = 50) {
  const query = useQuery({
    queryKey: [...AUTOMACOES_QUERY_KEY, "execucoes", limit],
    queryFn: () => api.get("/api/automacoes/execucoes", { limit }).then(unwrapData<Execucao[]>),
  });
  const data = query.data;
  return {
    ...query,
    execucoes: data ?? [],
    showSkeleton: query.isPending && !data,
    isRefreshing: query.isFetching && !!data,
  };
}

export function useAutomacaoMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: AUTOMACOES_QUERY_KEY });
  const criar = useMutation({
    mutationFn: (payload: AutomacaoInput) => api.post("/api/automacoes", payload).then(unwrapData<Automacao>),
    onSuccess: invalidate,
  });
  const atualizar = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: AutomacaoPatch }) =>
      api.patch(`/api/automacoes/${encodeURIComponent(id)}`, patch).then(unwrapData<Automacao>),
    onSuccess: invalidate,
  });
  const remover = useMutation({
    mutationFn: (id: string) => api.delete(`/api/automacoes/${encodeURIComponent(id)}`),
    onSuccess: invalidate,
  });
  return { criar, atualizar, remover };
}

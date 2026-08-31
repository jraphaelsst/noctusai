/**
 * Wrappers react-query sobre `api`. Uma função por endpoint do backend —
 * nenhuma tela monta URL na mão, e as chaves de cache ficam num lugar só.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, qs } from "@/lib/api";
import type {
  AmbienteProvedor,
  Captacao,
  Cliente,
  CredencialAmbiente,
  ClienteMetricas,
  Dashboard,
  Equipamento,
  Etapa,
  FormaCobranca,
  Imovel,
  Lancamento,
  Negocio,
  Producao,
  ProvedorEvento,
  ReceitaCliente,
  ResumoFinanceiro,
  Servico,
  StatusCredenciais,
} from "@/types";

// ── Cadastros ──────────────────────────────────────────────────────────────

export const useClientes = (incluirInativos = false) =>
  useQuery({
    queryKey: ["clientes", { incluirInativos }],
    queryFn: () => api.get<Cliente[]>(`/api/clientes${qs({ incluir_inativos: incluirInativos ? "true" : undefined })}`),
    placeholderData: (prev) => prev, // toggling "incluir inativos" keeps the list mounted instead of flashing a skeleton
  });

export const useClientesMetricas = () =>
  useQuery({
    queryKey: ["clientes-metricas"],
    queryFn: () => api.get<ClienteMetricas[]>("/api/clientes-metricas"),
  });

export const useImoveis = () =>
  useQuery({ queryKey: ["imoveis"], queryFn: () => api.get<Imovel[]>("/api/imoveis") });

export const useServicos = (incluirInativos = false) =>
  useQuery({
    queryKey: ["servicos", { incluirInativos }],
    queryFn: () => api.get<Servico[]>(`/api/servicos${qs({ incluir_inativos: incluirInativos ? "true" : undefined })}`),
    placeholderData: (prev) => prev, // toggling "incluir inativos" keeps the list mounted instead of flashing a skeleton
  });

export const useEquipamentos = (incluirInativos = false) =>
  useQuery({
    queryKey: ["equipamentos", { incluirInativos }],
    queryFn: () =>
      api.get<Equipamento[]>(`/api/equipamentos${qs({ incluir_inativos: incluirInativos ? "true" : undefined })}`),
    placeholderData: (prev) => prev, // toggling "incluir inativos" keeps the list mounted instead of flashing a skeleton
  });

// ── CRM ────────────────────────────────────────────────────────────────────

export const useNegocios = () =>
  useQuery({ queryKey: ["negocios"], queryFn: () => api.get<Negocio[]>("/api/negocios") });

export const useEtapasNegocio = () =>
  useQuery({
    queryKey: ["negocios", "etapas"],
    queryFn: () => api.get<Etapa[]>("/api/negocios/etapas"),
    staleTime: Infinity, // lista estática do backend
  });

// ── Agenda ─────────────────────────────────────────────────────────────────

export const useCaptacoes = (inicio?: string, fim?: string) =>
  useQuery({
    queryKey: ["captacoes", { inicio, fim }],
    queryFn: () => api.get<Captacao[]>(`/api/captacoes${qs({ inicio, fim })}`),
    placeholderData: (prev) => prev, // navigating the agenda window keeps the previous range mounted instead of flashing a skeleton
  });

// ── Produção ───────────────────────────────────────────────────────────────

export const useProducoes = () =>
  useQuery({ queryKey: ["producoes"], queryFn: () => api.get<Producao[]>("/api/producoes") });

export const useEtapasProducao = () =>
  useQuery({
    queryKey: ["producoes", "etapas"],
    queryFn: () => api.get<Etapa[]>("/api/producoes/etapas"),
    staleTime: Infinity,
  });

// ── Financeiro ─────────────────────────────────────────────────────────────

export const useLancamentos = (status?: string) =>
  useQuery({
    queryKey: ["financeiro", { status }],
    queryFn: () => api.get<Lancamento[]>(`/api/financeiro${qs({ status })}`),
    placeholderData: (prev) => prev, // changing the status filter keeps the list mounted instead of flashing a skeleton
  });

export const useResumoFinanceiro = () =>
  useQuery({
    queryKey: ["financeiro", "resumo"],
    queryFn: () => api.get<ResumoFinanceiro>("/api/financeiro/resumo"),
  });

export const useReceitaPorCliente = () =>
  useQuery({
    queryKey: ["financeiro", "por-cliente"],
    queryFn: () => api.get<ReceitaCliente[]>("/api/financeiro/por-cliente"),
  });

export const useStatusFinanceiro = () =>
  useQuery({
    queryKey: ["financeiro", "status"],
    queryFn: () => api.get<Etapa[]>("/api/financeiro/status"),
    staleTime: Infinity,
  });

/** Emite a cobrança no provedor (Asaas hoje, Banco do Brasil em produção). */
export const useEmitirCobranca = () =>
  useApiMutation<{ id: string; forma: FormaCobranca }, Lancamento>(
    ["financeiro", "dashboard"],
    ({ id, forma }) => api.post<Lancamento>(`/api/financeiro/${id}/cobranca`, { forma }),
    "Cobrança emitida",
  );

/** Reconsulta o provedor. É por aqui que o Banco do Brasil vai conciliar —
 * lá não há webhook, a baixa vem de consulta. */
export const useSincronizarCobranca = () =>
  useApiMutation<string, Lancamento>(
    ["financeiro", "dashboard"],
    (id) => api.post<Lancamento>(`/api/financeiro/${id}/sincronizar`),
    "Cobrança sincronizada",
  );

// ── Dashboard ──────────────────────────────────────────────────────────────

export const useDashboard = () =>
  useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/api/dashboard") });

// ── Mutations ──────────────────────────────────────────────────────────────

/**
 * Mutation genérica: roda a chamada e invalida as queries afetadas.
 * Ex.: `useApiMutation(["negocios", "dashboard"], fn, "Negócio salvo")`.
 */
export function useApiMutation<TArgs = any, TResult = any>(
  invalidate: string[],
  fn: (args: TArgs) => Promise<TResult>,
  successMessage?: string
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      invalidate.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
      if (successMessage) toast.success(successMessage);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Integração de cobrança ─────────────────────────────────────────────────
//
// `useEmitirCobranca` / `useSincronizarCobranca` (acima) existiam desde a
// migração 003 e NENHUMA tela as consumia — as rotas do backend estavam
// prontas e o produto não tinha por onde emitir uma cobrança. Estes hooks
// fecham o outro lado: credenciais, ambiente ativo e a fila de eventos.

export const useCredenciais = () =>
  useQuery({
    queryKey: ["integracoes", "credenciais"],
    queryFn: () => api.get<StatusCredenciais>("/api/integracoes/credenciais"),
  });

export const useSalvarCredencial = () =>
  useApiMutation<
    { ambiente: AmbienteProvedor; api_key: string; webhook_token?: string },
    CredencialAmbiente
  >(
    ["integracoes"],
    ({ ambiente, ...body }) =>
      api.put<CredencialAmbiente>(`/api/integracoes/credenciais/${ambiente}`, body),
    "Credencial salva"
  );

export const useRemoverCredencial = () =>
  useApiMutation<AmbienteProvedor, void>(
    ["integracoes"],
    (ambiente) => api.del<void>(`/api/integracoes/credenciais/${ambiente}`),
    "Credencial removida"
  );

export const useDefinirAmbiente = () =>
  useApiMutation<AmbienteProvedor, StatusCredenciais>(
    ["integracoes"],
    (ambiente) =>
      api.patch<StatusCredenciais>("/api/integracoes/credenciais/ativo", { ambiente }),
    "Ambiente alterado"
  );

/**
 * Lê o segredo do webhook em claro. `enabled` é obrigatório e default `false`:
 * o segredo só viaja quando alguém PEDE, nunca ao abrir a tela.
 */
export const useWebhookToken = (ambiente: AmbienteProvedor, enabled: boolean) =>
  useQuery({
    queryKey: ["integracoes", "webhook-token", ambiente],
    queryFn: () =>
      api.get<{ ambiente: AmbienteProvedor; webhook_token: string }>(
        `/api/integracoes/credenciais/${ambiente}/webhook-token`
      ),
    enabled,
    // Segredo não fica em cache além da sessão da tela.
    gcTime: 0,
    staleTime: 0,
  });

export const useRotacionarWebhookToken = () =>
  useApiMutation<AmbienteProvedor, { ambiente: AmbienteProvedor; webhook_token: string }>(
    ["integracoes"],
    (ambiente) =>
      api.post<{ ambiente: AmbienteProvedor; webhook_token: string }>(
        `/api/integracoes/credenciais/${ambiente}/webhook-token`
      ),
    "Token do webhook rotacionado"
  );

export const useEventosProvedor = () =>
  useQuery({
    queryKey: ["integracoes", "eventos"],
    queryFn: () => api.get<ProvedorEvento[]>("/api/integracoes/eventos"),
  });

export const useReprocessarEventos = () =>
  useApiMutation<void, { total: number; ok: number; erro: number }>(
    ["integracoes", "financeiro", "dashboard"],
    () => api.post<{ total: number; ok: number; erro: number }>("/api/integracoes/reprocessar"),
    "Fila reprocessada"
  );

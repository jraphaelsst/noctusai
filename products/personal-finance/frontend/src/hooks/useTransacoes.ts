import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Transacao } from "@/types";

interface FiltrosTransacoes {
  page?: number;
  page_size?: number;
  conta_id?: string;
  categoria_id?: string;
  tipo?: string;
  data_inicio?: string;
  data_fim?: string;
  busca?: string;
}

export function useTransacoes(filtros?: FiltrosTransacoes) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["transacoes", filtros],
    queryFn: async () => {
      const params: FiltrosTransacoes = {};
      if (filtros?.page) params.page = filtros.page;
      if (filtros?.page_size) params.page_size = filtros.page_size;
      if (filtros?.conta_id) params.conta_id = filtros.conta_id;
      if (filtros?.categoria_id) params.categoria_id = filtros.categoria_id;
      if (filtros?.tipo) params.tipo = filtros.tipo;
      if (filtros?.data_inicio) params.data_inicio = filtros.data_inicio;
      if (filtros?.data_fim) params.data_fim = filtros.data_fim;
      if (filtros?.busca) params.busca = filtros.busca;
      const result = await api.get("/api/transacoes", params);
      return result as { data: Transacao[]; total: number; page: number; page_size: number };
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useTransacao(id?: string) {
  return useQuery({
    queryKey: ["transacao", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/transacoes/${id}`);
      return result.data as Transacao;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useTransacoesPorCategoria(dataInicio?: string, dataFim?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["transacoes", "por-categoria", dataInicio, dataFim],
    queryFn: async () => {
      const params: { data_inicio?: string; data_fim?: string } = {};
      if (dataInicio) params.data_inicio = dataInicio;
      if (dataFim) params.data_fim = dataFim;
      const result = await api.get("/api/transacoes/por-categoria", params);
      return result.data;
    },
    enabled: !!user && !!dataInicio && !!dataFim,
    staleTime: 3 * 60 * 1000,
  });
}

/**
 * Shared onSuccess for all three transação mutations (wave-2 narrowing).
 * Every key here is backed by a read of the actual backend service
 * (`TransacoesService`), not a guess:
 *
 * - "transacoes" — the mutated resource itself. Keep.
 * - "contas" + "conta" — `_atualizar_saldo_conta` recomputes the affected
 *   account's `saldo` on every create/update/delete. "contas" (list) was
 *   already invalidated; "conta" (singular) is ADDED here — it was not
 *   before, and `ContaDetalhes.tsx` reads `useConta(id)` independently of
 *   the list, so a transação created elsewhere left that page showing a
 *   stale balance as current (exactly the risk this wave exists to close).
 *   Neither create nor update lets us target the one affected account id
 *   client-side for delete (the delete mutationFn only receives the id,
 *   not the row), so this stays a root-key invalidate rather than a
 *   per-account narrow.
 * - "orcamento" (singular family: `["orcamento", id, "progresso", mes]`),
 *   NOT "orcamentos" (the plain budget list) — `_sincronizar_orcamento`
 *   only ever writes `orcamento_itens.valor_gasto` for this transação's
 *   categoria+month, which `useOrcamentoProgresso` reads under the
 *   "orcamento" root (`useOrcamentos.ts`). The `Orcamento` rows themselves
 *   (nome/metodo/periodo/ativo) never change from a transação. The old
 *   "orcamentos" invalidation was therefore a WRONG-KEY bug, not just an
 *   over-broad one: it refetched a list that could never change and never
 *   touched the one query (budget "gasto" totals) that actually did.
 * - "dashboard" — `DashboardService.kpis()` reads `relatorios_service`
 *   (this month's receita/despesa) directly, and `.resumo()` returns
 *   `transacoes_recentes`. Keep.
 * - "relatorios" — left BROAD deliberately. `_invalidar_cache_mensal`
 *   confirms the transação's own month is recomputed server-side, but
 *   `useRelatorioAnual`/`useFluxoCaixa` cover arbitrary year/date ranges
 *   the frontend cannot evaluate against this transação's date. Unsure
 *   whether an open anual/fluxo-caixa query overlaps → keep, per the
 *   wave-2 bar ("when in doubt, leave the broad invalidation alone").
 * - "patrimonio" narrowed to `["patrimonio", "atual"]` —
 *   `PatrimonioService.calcular_atual()` reads live `contas.saldo` +
 *   `ativos.valor_atual`, so it moves with this transação.
 *   `["patrimonio", "historico"]` is snapshot rows written ONLY by
 *   `useCriarSnapshot` (`usePatrimonio.ts`) — a transação can never touch
 *   them, so refetching historico here was pure waste.
 */
function invalidateAposTransacao(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["transacoes"] });
  queryClient.invalidateQueries({ queryKey: ["contas"] });
  queryClient.invalidateQueries({ queryKey: ["conta"] });
  queryClient.invalidateQueries({ queryKey: ["orcamento"] });
  queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  queryClient.invalidateQueries({ queryKey: ["relatorios"] });
  queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
}

export function useCreateTransacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: Partial<Transacao>) => {
      const result = await api.post("/api/transacoes", data);
      return result.data as Transacao;
    },
    onSuccess: () => {
      invalidateAposTransacao(queryClient);
      toast.success("Transacao criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar transacao", { description: error.message });
    },
  });
}

export function useUpdateTransacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Transacao> & { id: string }) => {
      const result = await api.patch(`/api/transacoes/${id}`, data);
      return result.data as Transacao;
    },
    onSuccess: () => {
      invalidateAposTransacao(queryClient);
      toast.success("Transacao atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar transacao", { description: error.message });
    },
  });
}

export function useDeleteTransacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/transacoes/${id}`);
    },
    onSuccess: () => {
      invalidateAposTransacao(queryClient);
      toast.success("Transacao excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir transacao", { description: error.message });
    },
  });
}

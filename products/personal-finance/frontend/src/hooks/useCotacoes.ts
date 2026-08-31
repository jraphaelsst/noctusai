import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Cotacao } from "@/types";

export function useCotacao(ticker?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["cotacao", ticker],
    queryFn: async () => {
      if (!ticker) return null;
      const result = await api.get(`/api/cotacoes/${ticker}`);
      return result.data as Cotacao;
    },
    enabled: !!user && !!ticker,
    staleTime: 1 * 60 * 1000,
  });
}

export function useAtualizarPrecos() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const result = await api.post("/api/cotacoes/atualizar");
      return result.data;
    },
    onSuccess: () => {
      // DELIBERATELY LEFT BROAD (all but "patrimonio", see below) —
      // CotacoesService.atualizar_todos() loops every ativa carteira and
      // rewrites preco_atual/valor_atual/ganho_perda for EVERY holding
      // in the org (atualizar_precos_carteira, called per portfolio).
      // There is no narrower key to invalidate: "ativos" genuinely all
      // changed, "carteiras"/"carteira" (valor_total/resumo alloc, both
      // derived from ativos.valor_atual) genuinely all changed, and we
      // don't have the full ticker set client-side to scope "cotacao"
      // to just the ones that moved. This is the one mutation in this
      // file where "nukes the whole cache" is the CORRECT description
      // of what the backend actually did.
      queryClient.invalidateQueries({ queryKey: ["cotacao"] });
      queryClient.invalidateQueries({ queryKey: ["ativos"] });
      queryClient.invalidateQueries({ queryKey: ["carteiras"] });
      queryClient.invalidateQueries({ queryKey: ["carteira"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      // The one narrowing that IS safe here: "atual" (live sum) moves,
      // "historico" (immutable snapshot rows) does not.
      queryClient.invalidateQueries({ queryKey: ["patrimonio", "atual"] });
      toast.success("Precos atualizados com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar precos", { description: error.message });
    },
  });
}

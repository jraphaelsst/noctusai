/**
 * useRewards — React Query hooks for the rewards ledger + redemption.
 *
 * Phase 7 PROPER: wired to Engineer D's endpoints — GET /api/rewards/ledger
 * (distributor's accrual ledger), GET /api/rewards/rules (active reward
 * rules in the brand's org), POST /api/rewards/redeem (redemption request).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from "@noctusai/seed/infra";
import { toast } from "sonner";
import type { Reward, RewardRule } from "@/types";

export function useRewards() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["adconnect", "rewards", "ledger"],
    queryFn: async () => {
      const result = await api.get("/api/rewards/ledger");
      return (result.data || []) as Reward[];
    },
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

export function useRewardRules() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["adconnect", "rewards", "rules"],
    queryFn: async () => {
      const result = await api.get("/api/rewards/rules");
      return (result.data || []) as RewardRule[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRedeemRewards() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      valor_total: number;
      metodo: "credito_em_pedido" | "credito_em_fatura" | "reembolso_pix" | "outro";
      observacoes?: string;
    }) => {
      const result = await api.post("/api/rewards/redeem", data);
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "rewards", "ledger"] });
      toast.success("Resgate solicitado");
    },
    onError: (error: Error) => {
      toast.error("Erro ao solicitar resgate", { description: error.message });
    },
  });
}

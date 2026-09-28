/**
 * Cobrança (billing automation) hooks — CONTRACT.md (ninho-vazio) §Billing,
 * `/api/cobranca/*`.
 *
 * `dias_carencia` is the grace window a failed charge gets before the sweep
 * expires the subscription and moves the member to the free plan.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface CobrancaConfiguracoes {
  dias_carencia: number;
  automacoes_ativas: boolean;
}

export interface RelatorioRotina {
  nome: string;
  pulado: boolean;
  examinadas: number;
  alteradas: string[];
  erros: string[];
}

export interface ExecutarRotinaResponse {
  relatorios: RelatorioRotina[];
}

const cobrancaKeys = {
  configuracoes: ["cobranca", "configuracoes"] as const,
};

export function useCobrancaConfiguracoes(enabled = true) {
  return useQuery({
    queryKey: cobrancaKeys.configuracoes,
    queryFn: () => api.get<CobrancaConfiguracoes>("/api/cobranca/configuracoes"),
    enabled,
  });
}

export function useSalvarCobrancaConfiguracoes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CobrancaConfiguracoes) =>
      api.put<CobrancaConfiguracoes>("/api/cobranca/configuracoes", data),
    onSuccess: (data) => qc.setQueryData(cobrancaKeys.configuracoes, data),
  });
}

/** Runs the grace/expiry sweep now; the sweep can move members, subscriptions and cash. */
export function useExecutarRotinaCobranca() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<ExecutarRotinaResponse>("/api/cobranca/executar-rotina", {}),
    onSuccess: () => {
      for (const key of ["assinaturas", "membros", "dashboard", "lancamentos"]) {
        qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

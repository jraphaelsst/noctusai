/**
 * Julia › Análise de crédito (contract wave 13).
 *
 *   GET /api/julia/credito?status&page&page_size → {data:{items:[{id, contato_id, provider, status, resumo,
 *       created_at, updated_at, contato:{id,nome,telefone_e164,canal}}], total}}
 *   (an analysis only exists after the lead ACCEPTED consent — DB-enforced, so every row is consented)
 *   GET/PUT /api/julia/credito/config {ativo, provider, apenas_aluguel} (admin)
 *   POST /api/julia/credito/{contato_id}/reprocessar (admin)
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type CreditoStatus = "pendente" | "aprovado" | "reprovado" | "erro";
export interface CreditoItem {
  contato: { id: string; nome: string | null };
  status: CreditoStatus;
  resumo: string | null;
  created_at: string;
  updated_at: string | null;
}
export interface CreditoPage { items: CreditoItem[]; total: number }
export interface CreditoConfig { ativo: boolean; provider: string | null; apenas_aluguel: boolean; providers?: string[] }
export const CREDITO_PAGE_SIZE = 20;

const KEY = ["julia", "credito"] as const;

export function useJuliaCredito(status: "" | CreditoStatus, page: number) {
  return useQuery({
    queryKey: [...KEY, "lista", status, page],
    queryFn: async () => {
      const p = new URLSearchParams({ page: String(page), page_size: String(CREDITO_PAGE_SIZE) });
      if (status) p.set("status", status);
      const r = await api.get(`/api/julia/credito?${p}`);
      return (r.data ?? { items: [], total: 0 }) as CreditoPage;
    },
    placeholderData: keepPreviousData,
  });
}

export function useCreditoConfig() {
  return useQuery({
    queryKey: [...KEY, "config"],
    queryFn: async () => (await api.get("/api/julia/credito/config")).data as CreditoConfig,
  });
}

export function useSalvarCreditoConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (c: CreditoConfig) => (await api.put("/api/julia/credito/config", c)).data as CreditoConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useReprocessarCredito() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (contatoId: string) => api.post(`/api/julia/credito/${contatoId}/reprocessar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

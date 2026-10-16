/**
 * Lais › Análise de crédito (contract wave 13).
 *
 *   GET /api/lais/credito?status&page → {data:{items:[{contato, status, resumo, created_at,
 *       updated_at, consentimento}], total}}
 *   GET/PUT /api/lais/credito/config {ativo, provider, apenas_aluguel} (admin)
 *   POST /api/lais/credito/{contato_id}/reprocessar (admin)
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type CreditoStatus = "pendente" | "aprovado" | "reprovado" | "erro";
export interface CreditoItem {
  contato: { id: string; nome: string | null };
  status: CreditoStatus;
  resumo: string | null;
  created_at: string;
  updated_at: string;
  /** true/false = answered in chat; null = not asked yet. */
  consentimento: boolean | null;
}
export interface CreditoPage { items: CreditoItem[]; total: number }
export interface CreditoConfig { ativo: boolean; provider: string | null; apenas_aluguel: boolean }
export const CREDITO_PAGE_SIZE = 20;

const KEY = ["lais", "credito"] as const;

export function useLaisCredito(status: "" | CreditoStatus, page: number) {
  return useQuery({
    queryKey: [...KEY, "lista", status, page],
    queryFn: async () => {
      const p = new URLSearchParams({ page: String(page) });
      if (status) p.set("status", status);
      const r = await api.get(`/api/lais/credito?${p}`);
      return (r.data ?? { items: [], total: 0 }) as CreditoPage;
    },
    placeholderData: keepPreviousData,
  });
}

export function useCreditoConfig() {
  return useQuery({
    queryKey: [...KEY, "config"],
    queryFn: async () => (await api.get("/api/lais/credito/config")).data as CreditoConfig,
  });
}

export function useSalvarCreditoConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (c: CreditoConfig) => (await api.put("/api/lais/credito/config", c)).data as CreditoConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useReprocessarCredito() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (contatoId: string) => api.post(`/api/lais/credito/${contatoId}/reprocessar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

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
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { handOffToPolling, jobPolling } from "@noctusai/lib";

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
const LISTA_KEY = [...KEY, "lista"] as const;
/** A `pendente` analysis is waiting on the credit worker. */
const POLL_MS = 4000;
const temPendente = (d: CreditoPage | undefined) => !!d && d.items.some((i) => i.status === "pendente");

export function useJuliaCredito(status: "" | CreditoStatus, page: number) {
  return useQuery({
    queryKey: [...LISTA_KEY, status, page],
    queryFn: async () => {
      const p = new URLSearchParams({ page: String(page), page_size: String(CREDITO_PAGE_SIZE) });
      if (status) p.set("status", status);
      const r = await api.get(`/api/julia/credito?${p}`);
      return (r.data ?? { items: [], total: 0 }) as CreditoPage;
    },
    placeholderData: keepPreviousData,
    // The worker answers later: the list follows a pending analysis until it settles.
    ...jobPolling(temPendente, POLL_MS),
  });
}

export function useCreditoConfig() {
  return useQuery({
    queryKey: [...KEY, "config"],
    queryFn: async () => (await api.get("/api/julia/credito/config")).data as CreditoConfig,
  });
}

export function useSalvarCreditoConfig() {
  return useCacheWriteMutation<CreditoConfig, CreditoConfig>({
    mutationFn: async (c) => (await api.put("/api/julia/credito/config", c)).data as CreditoConfig,
    targets: [{ queryKey: [...KEY, "config"], commit: (_old, saved) => saved }],
    invalidate: [KEY],
  });
}

export function useReprocessarCredito() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — re-queues the credit check server-side and answers nothing; the new status arrives from the worker
    mutationFn: (contatoId: string) => api.post(`/api/julia/credito/${contatoId}/reprocessar`, {}),
    // Re-queued on the worker: hand the list off so it follows the new run (F87).
    onSuccess: () => handOffToPolling(qc, LISTA_KEY),
  });
}

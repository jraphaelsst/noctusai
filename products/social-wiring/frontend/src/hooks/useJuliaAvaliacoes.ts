/**
 * Lais › Avaliações no Google (contract wave 13).
 *
 *   GET /api/lais/avaliacoes?mes=YYYY-MM → {data:{pedidos_enviados, novas_avaliacoes,
 *       distribuicao:{"1".."5"}, media, total, ultimas[], configurado:{review_url, gbp}}}
 *   GET /api/lais/avaliacoes/config (member) · PUT (admin, partial)
 *       {google_review_url, gbp_location_id, capi_ativo, capi_pixel_id}
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface AvaliacaoGoogle { autor: string | null; nota: number; texto: string | null; data: string | null; link: string | null }
export interface AvaliacoesResumo {
  pedidos_enviados: number;
  novas_avaliacoes: number;
  distribuicao: Record<string, number>;
  media: number | null;
  total: number;
  ultimas: AvaliacaoGoogle[];
  configurado: { review_url: boolean; gbp: boolean };
}
export interface AvaliacoesConfig {
  google_review_url: string | null;
  gbp_location_id: string | null;
  capi_ativo: boolean;
  capi_pixel_id: string | null;
}

const KEY = ["lais", "avaliacoes"] as const;

export function mesAtual(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function useLaisAvaliacoes(mes: string) {
  return useQuery({
    queryKey: [...KEY, "resumo", mes],
    queryFn: async () => (await api.get(`/api/lais/avaliacoes?mes=${mes}`)).data as AvaliacoesResumo,
    placeholderData: keepPreviousData,
  });
}

export function useAvaliacoesConfig(enabled: boolean) {
  return useQuery({
    queryKey: [...KEY, "config"],
    enabled,
    queryFn: async () => (await api.get("/api/lais/avaliacoes/config")).data as AvaliacoesConfig,
  });
}

export function useSalvarAvaliacoesConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (c: Partial<AvaliacoesConfig>) => (await api.put("/api/lais/avaliacoes/config", c)).data as AvaliacoesConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

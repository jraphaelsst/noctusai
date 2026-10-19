/**
 * Julia › Captação (contract wave 8).
 *
 *   GET  /api/julia/captacoes?status&de&ate&page&page_size → {data:{items,total}}
 *   POST /api/julia/captacoes/{id}/registrar → {data:{imovel_id, imovel_codigo}}
 *   POST /api/julia/captacoes/{id}/descartar → 204
 *
 * Loading = two signals off `data` (never `isLoading`); `placeholderData: prev`
 * keeps the feed on screen while filters / page / page size change.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type CaptacaoStatus = "nova" | "registrada" | "descartada";
export type StatusFiltro = "" | CaptacaoStatus;
export const PAGE_SIZES = [5, 10, 15, 20] as const;

export interface JuliaCaptacao {
  id: string;
  contato: { id: string; nome: string | null; telefone: string | null };
  descricao: string | null;
  endereco: string | null;
  operacao: string | null;
  status: CaptacaoStatus;
  created_at: string;
  imovel_id: string | null;
  /** SW imóvel route key (`/imoveis/:codigo`); null until registered. */
  imovel_codigo: string | null;
}
export interface CaptacoesPage { items: JuliaCaptacao[]; total: number }
export interface CaptacaoFiltro { status: StatusFiltro; de: string; ate: string; page: number; pageSize: number }
export const FILTRO_VAZIO: CaptacaoFiltro = { status: "", de: "", ate: "", page: 1, pageSize: 10 };

const KEY = ["julia", "captacoes"] as const;

export function useJuliaCaptacoes(f: CaptacaoFiltro) {
  return useQuery({
    queryKey: [...KEY, f],
    queryFn: async () => {
      const p = new URLSearchParams({ page: String(f.page), page_size: String(f.pageSize) });
      if (f.status) p.set("status", f.status);
      if (f.de) p.set("de", f.de);
      if (f.ate) p.set("ate", f.ate);
      const r = await api.get(`/api/julia/captacoes?${p}`);
      return (r.data ?? { items: [], total: 0 }) as CaptacoesPage;
    },
    placeholderData: keepPreviousData,
  });
}

export function useRegistrarCaptacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      (await api.post(`/api/julia/captacoes/${id}/registrar`, {})).data as { imovel_id: string; imovel_codigo: string },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDescartarCaptacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/julia/captacoes/${id}/descartar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

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
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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

/** Every cached page / filter combination of the feed is reached by the prefix target. */
export function useRegistrarCaptacao() {
  return useCacheWriteMutation<{ imovel_id: string; imovel_codigo: string }, string>({
    mutationFn: async (id) =>
      (await api.post(`/api/julia/captacoes/${id}/registrar`, {})).data as { imovel_id: string; imovel_codigo: string },
    targets: (id) => [
      {
        queryKey: KEY,
        match: "prefix",
        optimistic: (old: CaptacoesPage | undefined) => pageOps.patch(old, id, { status: "registrada" }),
        commit: (old: CaptacoesPage | undefined, saved) =>
          pageOps.patch(old, id, { status: "registrada", imovel_id: saved.imovel_id, imovel_codigo: saved.imovel_codigo }),
      },
    ],
  });
}

export function useDescartarCaptacao() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.post(`/api/julia/captacoes/${id}/descartar`, {}),
    targets: (id) => [
      {
        queryKey: KEY,
        match: "prefix",
        optimistic: (old: CaptacoesPage | undefined) => pageOps.patch(old, id, { status: "descartada" }),
      },
    ],
  });
}

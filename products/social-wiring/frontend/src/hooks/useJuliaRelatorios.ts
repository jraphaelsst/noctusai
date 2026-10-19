/**
 * Julia › Relatórios (contract wave 10).
 *
 *   GET /api/julia/relatorios?operacao=&mes=YYYY-MM&aba=imoveis|bairros[&bairro=] → {data}
 *
 * Loading = two signals off `data` (never `isLoading`); the query is keyed by
 * every filter and keeps `placeholderData: prev` while the filters change.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type RelOperacao = "compra" | "aluguel";
export type RelAba = "imoveis" | "bairros";

export interface TipoLinha { tipo: string; pct_leads: number; pct_prateleira: number }
export interface ImovelLinha { codigo: string; tipo: string; preco: number; leads: number }
export interface RelImoveis { tipos: TipoLinha[]; top_imoveis: ImovelLinha[] }
export interface Desempenho {
  bairro: string;
  mediana_preco: number;
  pct_por_tipo: { tipo: string; pct: number }[];
  melhor_quartos: number | null;
  mais_buscados: ImovelLinha[];
}
export interface RelBairros {
  top_bairros: { bairro: string; leads: number }[];
  bairros_disponiveis: string[];
  desempenho: Desempenho | null;
}

export const RELATORIOS_KEY = ["sw", "julia", "relatorios"] as const;

export function mesAtual(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export const useRelatorioImoveis = (op: RelOperacao, mes: string, enabled = true) =>
  useRelatorioGated<RelImoveis>("imoveis", op, mes, enabled);
export const useRelatorioBairros = (op: RelOperacao, mes: string, bairro: string | undefined, enabled = true) =>
  useRelatorioGated<RelBairros>("bairros", op, mes, enabled, bairro);

function useRelatorioGated<T>(aba: RelAba, op: RelOperacao, mes: string, enabled: boolean, bairro?: string) {
  const q = useQuery({
    queryKey: [...RELATORIOS_KEY, aba, op, mes, bairro ?? ""],
    enabled,
    queryFn: async () => {
      const p = new URLSearchParams({ operacao: op, mes, aba });
      if (bairro) p.set("bairro", bairro);
      return (await api.get<{ data: T }>(`/api/julia/relatorios?${p.toString()}`)).data;
    },
    placeholderData: keepPreviousData,
  });
  return { ...q, showSkeleton: enabled && q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

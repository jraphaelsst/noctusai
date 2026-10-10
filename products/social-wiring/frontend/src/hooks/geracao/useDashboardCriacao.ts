/**
 * Dashboard de Criação de mídia (P1) over `GET /api/media-creation/dashboard`
 * (contract §4.7 #49). The response arrives wrapped in `{success, data}`.
 *
 * Loading rule (lying-loading-state.md): `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data`, never `isLoading`. Changing the marca
 * or the Histórico order keeps the previous payload on screen while it refetches.
 * The query key sits under `["sw","geracao"]`, so every headline / roteiro
 * mutation refreshes the dashboard too.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { DashboardCriacao } from "@/types/geracao";
import { GERACAO_KEY } from "./useHeadlineMutations";

interface Envelope<T> {
  success?: boolean;
  data: T;
}

export type HistoricoOrdem = "data_desc" | "data_asc" | "tipo";

export const HISTORICO_ORDEM_ROTULO: Record<HistoricoOrdem, string> = {
  data_desc: "Data decrescente",
  data_asc: "Data crescente",
  tipo: "Tipo",
};

export function useDashboardCriacao(marcaId: string | null, ordem: HistoricoOrdem = "data_desc") {
  const query = useQuery({
    queryKey: [...GERACAO_KEY, "dashboard", marcaId, ordem] as const,
    enabled: !!marcaId,
    queryFn: async () => {
      const p = new URLSearchParams({ marca_id: marcaId as string, historico_ordem: ordem });
      return (await api.get<Envelope<DashboardCriacao>>(`/api/media-creation/dashboard?${p}`)).data;
    },
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

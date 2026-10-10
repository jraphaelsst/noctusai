/**
 * Meu Perfil — "Informações de criação" per marca (contract §4.1 #2/#3).
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 * The bio is the same field as the Cérebro bio card, so a save also invalidates `["sw","cerebro"]`.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { CEREBRO_KEY } from "@/hooks/useCerebro";
import type { PerfilCriacao } from "@/types/geracao";

interface Envelope<T> {
  success?: boolean;
  data: T;
}

const BASE = "/api/media-creation/perfil";
export const perfilCriacaoKey = (marcaId: string | null) => ["sw", "geracao", "perfil", marcaId] as const;

export type PerfilCriacaoInput = Partial<Omit<PerfilCriacao, "marca_id" | "updated_at">>;

export function usePerfilCriacao(marcaId: string | null) {
  const query = useQuery({
    queryKey: perfilCriacaoKey(marcaId),
    enabled: !!marcaId,
    queryFn: async () =>
      (await api.get<Envelope<PerfilCriacao>>(`${BASE}?marca_id=${encodeURIComponent(marcaId as string)}`)).data,
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useSalvarPerfilCriacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { marca_id: string } & PerfilCriacaoInput) =>
      (await api.put<Envelope<PerfilCriacao>>(BASE, v)).data,
    onSuccess: (data) => {
      qc.setQueryData(perfilCriacaoKey(data.marca_id), data);
      void qc.invalidateQueries({ queryKey: ["sw", "geracao", "perfil"] });
      void qc.invalidateQueries({ queryKey: CEREBRO_KEY });
    },
  });
}

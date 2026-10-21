/**
 * Treinamentos (contract §4.2 #4/#5 + `GET /treinamentos/admin`).
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import type { Treinamento } from "@/types/geracao";

interface Envelope<T> {
  success?: boolean;
  data: T;
}

const BASE = "/api/media-creation/treinamentos";
export const TREINAMENTOS_KEY = ["sw", "geracao", "treinamentos"] as const;

export function useTreinamentos() {
  const query = useQuery({
    queryKey: TREINAMENTOS_KEY,
    queryFn: async () => (await api.get<Envelope<Treinamento[]>>(BASE)).data,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/** Whether the caller is a platform admin (shows the edit controls; the server enforces). */
export function useTreinamentosAdmin() {
  return useQuery({
    queryKey: [...TREINAMENTOS_KEY, "admin"] as const,
    queryFn: async () => (await api.get<Envelope<{ is_admin: boolean }>>(`${BASE}/admin`)).data.is_admin,
  });
}

export type TreinamentoInput = Partial<Pick<Treinamento, "titulo" | "descricao" | "video_url" | "ativo" | "ordem">>;

export function useAtualizarTreinamento() {
  return useCacheWriteMutation<Treinamento, { id: string } & TreinamentoInput>({
    mutationFn: async (v) => {
      const { id, ...body } = v;
      return (await api.put<Envelope<Treinamento>>(`${BASE}/${encodeURIComponent(id)}`, body)).data;
    },
    targets: [
      {
        queryKey: TREINAMENTOS_KEY,
        optimistic: (old: Treinamento[] | undefined, { id, ...changes }) => listOps.patch(old, id, changes),
        commit: (old: Treinamento[] | undefined, saved) => listOps.replace(old, saved.id, saved),
      },
    ],
  });
}

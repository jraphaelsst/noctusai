/**
 * Config of the Vista-vs-ours divergence digest (owner 2026-11-04). TRANSITIONAL — NOC-REMEDIATE[transicao-vista-divergencias]:
 * self-contained so it is deleted together with the rest of the divergence mechanism.
 *
 *   GET /api/imoveis/divergencias/config → {data:{ativa, destino_user_id}}   (org admin)
 *   PUT /api/imoveis/divergencias/config {ativa?, destino_user_id?}  → {data:{...}}  (omitted key = untouched;
 *       `destino_user_id: null` clears the destination)
 *
 * The phone is resolved server-side from the platform user — never typed here.
 */
import { useQuery } from "@tanstack/react-query";

import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

export interface DivergenciasConfig {
  ativa: boolean;
  destino_user_id: string | null;
}

export type DivergenciasConfigPatch = Partial<DivergenciasConfig>;

export const DIVERGENCIAS_CONFIG_KEY = ["sw", "imoveis", "divergencias", "config"] as const;
const URL = "/api/imoveis/divergencias/config";

export function useDivergenciasConfig(enabled = true) {
  const query = useQuery({
    queryKey: DIVERGENCIAS_CONFIG_KEY,
    queryFn: async () => (await api.get<{ data: DivergenciasConfig }>(URL)).data,
    enabled,
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useSalvarDivergenciasConfig() {
  return useCacheWriteMutation<DivergenciasConfig, DivergenciasConfigPatch>({
    mutationFn: async (patch) => (await api.put<{ data: DivergenciasConfig }>(URL, patch)).data,
    targets: [
      {
        queryKey: DIVERGENCIAS_CONFIG_KEY,
        // The change is exactly what was asked: draw it now, replaced by the server's answer on commit.
        optimistic: (old: DivergenciasConfig | undefined, patch) =>
          old ? { ...old, ...patch } : undefined,
        commit: (_old: DivergenciasConfig | undefined, saved) => saved,
      },
    ],
  });
}

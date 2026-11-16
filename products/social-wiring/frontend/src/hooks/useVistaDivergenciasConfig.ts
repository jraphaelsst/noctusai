/**
 * Config of the Vista sync (owner 2026-11-04: Vista wins, every change lands in the imóvel history; 2026-11-15: the switchable
 * WhatsApp digest of opened approvals + its destination user are KEPT). TRANSITIONAL —
 * NOC-REMEDIATE[transicao-vista-divergencias]: self-contained so it is deleted with the rest of the mechanism.
 *
 *   GET /api/imoveis/divergencias/config → {data:{ativa, vista_escrita_ativa, destino_user_id, vista_escrita_disponivel}}   (org admin)
 *   PUT /api/imoveis/divergencias/config {ativa?, vista_escrita_ativa?, destino_user_id?} → {data:{...}}  (omitted key = untouched;
 *       `destino_user_id: null` clears the destination)
 *
 * `vista_escrita_disponivel` is the server's cached probe of the API key's write grant: true / false / null (unknown).
 * Read-only for the UI; the key never reaches the browser.
 */
import { useQuery } from "@tanstack/react-query";

import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

export interface DivergenciasConfig {
  /** Keep imóveis up to date with Vista (the sync's mirror + history). */
  ativa: boolean;
  /** The owner's switch: write to Vista when the owner confirms via Julia. Default OFF. */
  vista_escrita_ativa: boolean;
  /** Who gets the WhatsApp digest of opened approvals (kept 2026-11-15; null = in-app only). */
  destino_user_id: string | null;
  /** Does the key permit writing to Vista? null = unknown. */
  vista_escrita_disponivel: boolean | null;
}

export type DivergenciasConfigPatch = Partial<Pick<DivergenciasConfig, "ativa" | "vista_escrita_ativa" | "destino_user_id">>;

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

/**
 * `GET /api/guia-documentos` — the documents / certidões / lead-flow guide.
 *
 * ONE query for every consumer: the "Guia de documentos" page and every "i"
 * popover on the card (`components/guia/GuiaInfo.tsx`) read the same cache
 * entry. The payload is derived from code catalogs, so it only changes on a
 * deploy — a long `staleTime` (1h) means opening fifty "i"s costs one request.
 *
 * Loading contract (KB § PATTERNS/frontend/lying-loading-state.md):
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 * Read-only: no mutations exist for this surface.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { GuiaDocumentos } from "@/types/guiaDocumentos";

export const GUIA_DOCUMENTOS_KEY = ["sw", "guia-documentos"] as const;
export const GUIA_DOCUMENTOS_PATH = "/api/guia-documentos";

const UMA_HORA = 60 * 60 * 1000;

export function useGuiaDocumentos() {
  const q = useQuery({
    queryKey: GUIA_DOCUMENTOS_KEY,
    queryFn: () => api.get<GuiaDocumentos>(GUIA_DOCUMENTOS_PATH),
    staleTime: UMA_HORA,
    gcTime: UMA_HORA,
  });
  return {
    ...q,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
  };
}

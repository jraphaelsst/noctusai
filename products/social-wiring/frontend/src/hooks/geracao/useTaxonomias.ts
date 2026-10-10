/**
 * Static Geração taxonomies (nichos, profissões, formatos, gatilhos, tons) —
 * contract §4.1 #1. They never change at runtime, so they are cached for the session.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { Taxonomias } from "@/types/geracao";

interface Envelope<T> {
  success?: boolean;
  data: T;
}

export const TAXONOMIAS_KEY = ["sw", "geracao", "taxonomias"] as const;

export function useTaxonomias() {
  const query = useQuery({
    queryKey: TAXONOMIAS_KEY,
    queryFn: async () => (await api.get<Envelope<Taxonomias>>("/api/media-creation/taxonomias")).data,
    staleTime: Infinity,
  });
  return { ...query, showSkeleton: query.isPending && !query.data };
}

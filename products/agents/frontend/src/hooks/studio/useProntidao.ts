/**
 * Agent Studio — readiness checklist: `GET /api/studio/agents/{key}/prontidao`.
 * Read-only, derived on the server from the draft; it is re-read (never edited locally) whenever the
 * draft changes, so every draft-writing hook invalidates `studioKeys.prontidao`.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Prontidao } from "@/api/studio/types-prontidao";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

export function useProntidao(key: string, enabled = true) {
  const q = useQuery<Prontidao>({
    queryKey: studioKeys.prontidao(key),
    queryFn: () => api.get<Prontidao>(`/api/studio/agents/${seg(key)}/prontidao`),
    enabled: !!key && enabled,
    retry: false,
    staleTime: 0,
    placeholderData: keepWithinAgent<Prontidao>(key),
  });
  return toView(q);
}

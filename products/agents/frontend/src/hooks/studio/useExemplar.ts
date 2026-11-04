/**
 * Agent Studio — "usar como referência" flag: `PUT /api/studio/plataforma/agentes/{key}/exemplar {exemplar}`
 * (platform admin). The flag is drawn at once on the agent's list row and detail (optimistic, rolled back on
 * refusal by `useCacheWriteMutation`) and settled by a background refetch.
 */
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { AgentDetail, AgentListResponse } from "@/api/studio/types";
import { seg, studioKeys } from "./keys";

export function useSetExemplar(key: string) {
  return useCacheWriteMutation<unknown, { exemplar: boolean }>({
    mutationFn: (vars) => api.put<unknown>(`/api/studio/plataforma/agentes/${seg(key)}/exemplar`, vars),
    targets: [
      {
        queryKey: studioKeys.list(),
        optimistic: (old: AgentListResponse | undefined, vars) =>
          old ? { ...old, items: old.items.map((a) => (a.key === key ? { ...a, exemplar: vars.exemplar } : a)) } : old,
      },
      {
        queryKey: studioKeys.detail(key),
        optimistic: (old: AgentDetail | undefined, vars) => (old ? { ...old, exemplar: vars.exemplar } : old),
      },
    ],
    invalidate: [studioKeys.list(), studioKeys.detail(key)],
  });
}

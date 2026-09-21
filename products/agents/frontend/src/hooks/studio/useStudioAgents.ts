/**
 * Agent Studio — agents (CONTRACT §D1):
 *   GET   /api/studio/agents
 *   POST  /api/studio/agents            (admin)
 *   GET   /api/studio/agents/{key}
 *   PATCH /api/studio/agents/{key}      (admin)
 *
 * Writes are admin-only server-side (`require_admin`); pages also hide the
 * controls for members via `useIsAdmin()`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AgentCreateInput,
  AgentDetail,
  AgentListResponse,
  AgentPatchInput,
  AgentSummary,
} from "@/api/studio/types";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

export function useStudioAgents() {
  const q = useQuery<AgentListResponse>({
    queryKey: studioKeys.list(),
    queryFn: () => api.get<AgentListResponse>("/api/studio/agents"),
  });
  const view = toView(q);
  return { ...view, data: q.data?.items };
}

export function useStudioAgent(key: string) {
  const q = useQuery<AgentDetail>({
    queryKey: studioKeys.detail(key),
    queryFn: () => api.get<AgentDetail>(`/api/studio/agents/${seg(key)}`),
    enabled: !!key,
    // A 404 / 409 `not_studio_agent` is an answer, not a blip.
    retry: false,
    placeholderData: keepWithinAgent<AgentDetail>(key),
  });
  return toView(q);
}

export function useCreateStudioAgent() {
  const qc = useQueryClient();
  return useMutation<AgentSummary, unknown, AgentCreateInput>({
    mutationFn: (payload) => api.post<AgentSummary>("/api/studio/agents", payload),
    onSuccess: (created) => {
      qc.setQueryData<AgentListResponse>(studioKeys.list(), (prev) =>
        prev ? { ...prev, items: [...prev.items, created] } : prev,
      );
      void qc.invalidateQueries({ queryKey: studioKeys.list() });
    },
  });
}

export function useUpdateStudioAgent(key: string) {
  const qc = useQueryClient();
  return useMutation<AgentSummary, unknown, AgentPatchInput>({
    mutationFn: (payload) => api.patch<AgentSummary>(`/api/studio/agents/${seg(key)}`, payload),
    onSuccess: (updated) => {
      qc.setQueryData<AgentListResponse>(studioKeys.list(), (prev) =>
        prev ? { ...prev, items: prev.items.map((a) => (a.key === updated.key ? updated : a)) } : prev,
      );
      qc.setQueryData<AgentDetail>(studioKeys.detail(key), (prev) =>
        prev ? { ...prev, ...updated } : prev,
      );
      // `publicacao_limiar` feeds the publish gate; the compiled view does not
      // depend on agent fields other than `nome`, which changes rarely enough
      // that a targeted refetch is simpler than reasoning about it.
      void qc.invalidateQueries({ queryKey: studioKeys.compiledAll(key) });
    },
  });
}

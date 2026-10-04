/**
 * Agent Studio — agent packages (CONTRACT §G3/§H2/§I):
 *   GET   /api/studio/agents/{key}/projects                 (member)
 *   GET   /api/studio/agents/{key}/learnings?project&status (member)
 *   PATCH /api/studio/agents/{key}/learnings/{id}           (admin)
 *
 * The review is optimistic: the row flips immediately, rolls back on error,
 * and always settles with an invalidation.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Learning,
  LearningListResponse,
  LearningReviewInput,
  PackageProject,
  PackageProjectsResponse,
} from "@/api/studio/types-packages";
import { keepWithinAgent, seg, toView } from "./keys";

export const packageKeys = {
  projects: (key: string) => ["studio", key, "package-projects"] as const,
  learningsAll: (key: string) => ["studio", key, "learnings"] as const,
  learnings: (key: string, project: string, status: string) =>
    ["studio", key, "learnings", project, status] as const,
};

const base = (key: string) => `/api/studio/agents/${seg(key)}`;

export function usePackageProjects(key: string) {
  const q = useQuery<PackageProjectsResponse>({
    queryKey: packageKeys.projects(key),
    queryFn: () => api.get<PackageProjectsResponse>(`${base(key)}/projects`),
    enabled: !!key,
    placeholderData: keepWithinAgent<PackageProjectsResponse>(key),
  });
  const view = toView(q);
  return { ...view, data: q.data?.items as PackageProject[] | undefined };
}

export function useLearnings(key: string, project: string, status: string) {
  const q = useQuery<LearningListResponse>({
    queryKey: packageKeys.learnings(key, project, status),
    queryFn: () => {
      const params = new URLSearchParams();
      if (project) params.set("project", project);
      if (status) params.set("status", status);
      const qs = params.toString();
      return api.get<LearningListResponse>(`${base(key)}/learnings${qs ? `?${qs}` : ""}`);
    },
    enabled: !!key,
    // Filter changes keep the list mounted within the same agent.
    placeholderData: keepWithinAgent<LearningListResponse>(key),
  });
  const view = toView(q);
  return { ...view, data: q.data?.items as Learning[] | undefined };
}

type Snapshot = [readonly unknown[], LearningListResponse | undefined][];

export function useReviewLearning(key: string) {
  const qc = useQueryClient();
  return useMutation<Learning, unknown, { id: string; review: LearningReviewInput }, { snapshot: Snapshot }>({
    mutationFn: ({ id, review }) => api.patch<Learning>(`${base(key)}/learnings/${seg(id)}`, review),
    onMutate: async ({ id, review }) => {
      await qc.cancelQueries({ queryKey: packageKeys.learningsAll(key) });
      const snapshot = qc.getQueriesData<LearningListResponse>({ queryKey: packageKeys.learningsAll(key) });
      qc.setQueriesData<LearningListResponse>({ queryKey: packageKeys.learningsAll(key) }, (prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((l) => (l.id === id ? { ...l, status: review.status, nota: review.nota } : l)),
            }
          : prev,
      );
      return { snapshot };
    },
    onError: (_err, _vars, ctx) => {
      ctx?.snapshot.forEach(([k, data]) => qc.setQueryData(k, data));
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: packageKeys.learningsAll(key) });
    },
  });
}

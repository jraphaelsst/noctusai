/**
 * Example hooks — the canonical shape every domain hook in a new product follows.
 *
 *   - reads are TanStack queries keyed by one `exampleKeys` factory;
 *   - render state is the two-signal rule: `showSkeleton = isPending && !data`,
 *     `isRefreshing = isFetching && !!data`, never `isLoading`
 *     (KB § PATTERNS/frontend/lying-loading-state.md);
 *   - every write goes through `useCacheWriteMutation`: it draws the change
 *     when the result is predictable, commits the server's answer the moment
 *     it arrives, and only then refetches in the background. A write that
 *     merely invalidates makes the screen wait for write + refetch and is
 *     refused at commit by `check_mutation_invalidate_only`
 *     (KB § PATTERNS/frontend/mutation-cache-writes.md);
 *   - `api` comes from `@/lib/api` (the local test seam).
 *
 * A plain CRUD resource can use the seed factory instead of hand-writing
 * these: `createCrudHooks` from `@noctusai/lib/hooks` follows the same
 * contract.
 *
 * TODO(new-product): rename `Example` → your domain (`Video`, `Order`, …);
 * replace the URL + types with your real endpoint. Backend mirror lives at
 * `app/routers/example_router.py`.
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";

// ─── Types (mirror backend schemas/example.py) ─────────────────────────
export interface Example {
  id: string;
  org_id: string;
  title: string;
  description: string | null;
  created_at: string;
}

export type ExampleCreate = Pick<Example, "title" | "description">;
export type ExampleUpdate = Partial<ExampleCreate>;

export const exampleKeys = {
  all: ["examples"] as const,
  list: () => [...exampleKeys.all, "list"] as const,
  detail: (id: string) => [...exampleKeys.all, "detail", id] as const,
};

// ─── Reads ─────────────────────────────────────────────────────────────
export function useExamples() {
  const query = useQuery({
    queryKey: exampleKeys.list(),
    queryFn: () => api.get<Example[]>("/api/example"),
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

// ─── Writes ────────────────────────────────────────────────────────────
/** Optimistic + commit: the row is on screen on click, swapped for the server's row when it answers. */
export function useCreateExample() {
  return useCacheWriteMutation<Example, ExampleCreate>({
    mutationFn: (payload) => api.post<Example>("/api/example", payload),
    targets: [
      {
        queryKey: exampleKeys.list(),
        optimistic: (old: Example[] | undefined, payload, { tempId }) =>
          listOps.append(old, {
            id: tempId,
            org_id: "",
            created_at: new Date().toISOString(),
            ...payload,
          }),
        commit: (old: Example[] | undefined, saved, _payload, { tempId }) =>
          listOps.replace(old, tempId, saved),
      },
    ],
  });
}

/** The edit is drawn in the list and the detail, then replaced by the server's row. */
export function useUpdateExample() {
  return useCacheWriteMutation<Example, { id: string; changes: ExampleUpdate }>({
    mutationFn: ({ id, changes }) => api.patch<Example>(`/api/example/${id}`, changes),
    targets: ({ id }) => [
      {
        queryKey: exampleKeys.list(),
        optimistic: (old: Example[] | undefined, { changes }) => listOps.patch<Example>(old, id, changes),
        commit: (old: Example[] | undefined, saved) => listOps.replace(old, id, saved),
      },
      {
        queryKey: exampleKeys.detail(id),
        optimistic: (old: Example | undefined, { changes }) => listOps.merge(old, changes),
        commit: (old: Example | undefined, saved) => (old === undefined ? undefined : saved),
      },
    ],
  });
}

/** Leaves the list on click; a failed delete puts it back. */
export function useDeleteExample() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`/api/example/${id}`),
    targets: [
      {
        queryKey: exampleKeys.list(),
        optimistic: (old: Example[] | undefined, id) => listOps.remove(old, id),
      },
    ],
  });
}

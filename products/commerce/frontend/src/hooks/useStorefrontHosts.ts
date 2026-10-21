/**
 * Storefront hosts (CONTRACT §3 `GET/POST /api/commerce/hosts`,
 * `DELETE …/{hostname}`) — platform-admin only, decided by the SERVER.
 *
 * The 403 a non-admin gets is not an error state for the page: it IS the
 * answer to "may I manage hosts?" (`forbidden`), and `useIsPlatformAdmin`
 * reads the same query so the store-profile form only offers the
 * platform-fee field to a caller the server already accepted as staff.
 *
 * NOC-REMEDIATE[commerce-organ-hook-gap]: the organ's `createCommerceHooks`
 * has no hosts hooks; lift these into `seed/lib/frontend/src/commerce/hooks.ts`
 * (CONTRACT-DELTAS D2).
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { apiErrorStatus, commerceKeys } from "@noctusai/lib";

import { api } from "@/lib/api";

export interface StorefrontHost {
  hostname: string;
  org_id: string;
  is_primary: boolean;
  created_at?: string;
}

export const hostsKey = [...commerceKeys.all, "staff", "hosts"] as const;

export function useStorefrontHosts() {
  const q = useQuery<StorefrontHost[]>({
    queryKey: hostsKey,
    queryFn: async () => (await api.get<{ data: StorefrontHost[] }>("/api/commerce/hosts")).data,
    // A 403 is a definitive answer, not a transient failure.
    retry: (count, err) => apiErrorStatus(err) !== 403 && count < 2,
  });
  const forbidden = apiErrorStatus(q.error) === 403;
  return {
    data: q.data,
    error: q.error,
    forbidden,
    refetch: q.refetch,
    showSkeleton: q.isPending && !q.data && q.fetchStatus !== "idle",
    isRefreshing: q.isFetching && !!q.data,
  };
}

export function useStorefrontHostMutations() {
  // Hosts are keyed by `hostname` (no `id`), which the seed `listOps` do not address
  // (seed gap: an idKey option) — the two one-line array edits below are inline.
  return {
    add: useCacheWriteMutation<StorefrontHost, { hostname: string; is_primary: boolean }>({
      mutationFn: async (body) =>
        (await api.post<{ data: StorefrontHost }>("/api/commerce/hosts", body)).data,
      // Making a host primary demotes the previous primary server-side: that
      // consequence converges on the settle refetch; the new host shows now.
      targets: [
        {
          queryKey: hostsKey,
          commit: (old: StorefrontHost[] | undefined, saved) =>
            Array.isArray(old) ? [...old.filter((h) => h.hostname !== saved.hostname), saved] : old,
        },
      ],
    }),
    remove: useCacheWriteMutation<unknown, string>({
      mutationFn: (hostname) => api.delete(`/api/commerce/hosts/${encodeURIComponent(hostname)}`),
      targets: [
        {
          queryKey: hostsKey,
          optimistic: (old: StorefrontHost[] | undefined, hostname) =>
            Array.isArray(old) ? old.filter((h) => h.hostname !== hostname) : old,
        },
      ],
    }),
  };
}

/**
 * UX hint only (the server enforces): true once the server answered the
 * platform-admin-only hosts listing with 200.
 */
export function useIsPlatformAdmin(): boolean {
  const hosts = useStorefrontHosts();
  return !!hosts.data && !hosts.forbidden;
}

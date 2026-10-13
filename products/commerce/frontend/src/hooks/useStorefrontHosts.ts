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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: hostsKey });
  return {
    add: useMutation({
      mutationFn: async (body: { hostname: string; is_primary: boolean }) =>
        (await api.post<{ data: StorefrontHost }>("/api/commerce/hosts", body)).data,
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (hostname: string) => api.delete(`/api/commerce/hosts/${encodeURIComponent(hostname)}`),
      onSuccess: done,
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

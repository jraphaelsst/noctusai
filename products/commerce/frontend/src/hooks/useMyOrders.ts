/**
 * "Minhas compras" via the e-mailed magic link (CONTRACT-DELTAS A1:
 * `GET /api/storefront/my-orders?token=` → `PublicOrder[]`). The token is
 * HMAC-signed and bound to the store + purpose server-side.
 *
 * No `placeholderData`: authorisation-scoped personal data keyed by token —
 * another token's orders must never show under a new key.
 *
 * NOC-REMEDIATE[commerce-organ-hook-gap]: lift into the organ's
 * `createCommerceHooks` (CONTRACT-DELTAS D2).
 */
import { useQuery } from "@tanstack/react-query";
import { apiErrorStatus, commerceKeys, type PublicOrder } from "@noctusai/lib";

import { storefrontTransport } from "@/lib/commerce";

export function useMyOrders(token: string | null) {
  const q = useQuery<PublicOrder[]>({
    queryKey: [...commerceKeys.all, "storefront", "my-orders", token ?? ""],
    queryFn: async () =>
      (await storefrontTransport.get<{ data: PublicOrder[] }>("/api/storefront/my-orders", { token })).data,
    enabled: !!token,
    // 4xx (expired / tampered link) is definitive; only retry transport hiccups.
    retry: (count, err) => (apiErrorStatus(err) ?? 500) >= 500 && count < 2,
  });
  return {
    data: q.data,
    error: q.error,
    isError: q.isError,
    refetch: q.refetch,
    showSkeleton: q.isPending && !q.data && q.fetchStatus !== "idle",
    isRefreshing: q.isFetching && !!q.data,
  };
}

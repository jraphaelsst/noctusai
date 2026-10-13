/**
 * Confirms a storefront privacy request from its e-mailed link
 * (CONTRACT-DELTAS A1: `POST /api/storefront/privacy-requests/verify {token}`
 * → `{status, kind}`). The server transition is idempotent (`open → verified`;
 * an already-verified request answers its current state), so it is modelled
 * as a query: one call per token, cached, no double-fire side effects.
 *
 * NOC-REMEDIATE[commerce-organ-hook-gap]: lift into the organ's
 * `createCommerceHooks` (CONTRACT-DELTAS D2).
 */
import { useQuery } from "@tanstack/react-query";
import { apiErrorStatus, commerceKeys, type PrivacyRequestKind, type PrivacyRequestStatus } from "@noctusai/lib";

import { storefrontTransport } from "@/lib/commerce";

export interface PrivacyVerifyResult {
  status: PrivacyRequestStatus;
  kind: PrivacyRequestKind;
}

export function usePrivacyVerify(token: string | null) {
  const q = useQuery<PrivacyVerifyResult>({
    queryKey: [...commerceKeys.all, "storefront", "privacy-verify", token ?? ""],
    queryFn: async () =>
      (await storefrontTransport.post<{ data: PrivacyVerifyResult }>("/api/storefront/privacy-requests/verify", { token }))
        .data,
    enabled: !!token,
    staleTime: Infinity,
    retry: (count, err) => (apiErrorStatus(err) ?? 500) >= 500 && count < 2,
  });
  return {
    data: q.data,
    error: q.error,
    isError: q.isError,
    refetch: q.refetch,
    showSkeleton: q.isPending && !q.data && q.fetchStatus !== "idle",
  };
}

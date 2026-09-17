/**
 * Plano gateway-refs hooks — community-m2-contract.md §Endpoints#Gateway-refs.
 *
 * Maps a manager-made tier (`planos`, module 1) to each gateway's own object
 * (a Stripe Price id or an Asaas plan reference). One row per
 * `(plano_id, gateway)`; a plan can have zero, one, or two refs (card via
 * Stripe, Pix/boleto via Asaas). Consumed by `Planos.tsx`'s per-row
 * "Gateways" dialog (module 1's page, EXTENDED — not rewritten).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type Gateway = "stripe" | "asaas";

export interface GatewayRef {
  plano_id: string;
  gateway: Gateway;
  ref_externo: string;
  updated_at: string;
}

export interface GatewayRefListResponse {
  items: GatewayRef[];
  total: number;
}

const gatewayRefsKeys = {
  list: (planoId: string) => ["planos", planoId, "gateway-refs"] as const,
};

/** Admin-only per module 1's role rule (reads: admin+moderador; writes: admin). */
export function useGatewayRefs(planoId?: string | null) {
  return useQuery({
    queryKey: gatewayRefsKeys.list(planoId ?? ""),
    queryFn: () => api.get<GatewayRefListResponse>(`/api/planos/${planoId}/gateway-refs`),
    enabled: !!planoId,
  });
}

/** Upsert — creating returns 200, not 201, because the key is the path. */
export function useSetGatewayRef(planoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ gateway, ref_externo }: { gateway: Gateway; ref_externo: string }) =>
      api.put<GatewayRef>(`/api/planos/${planoId}/gateway-refs/${gateway}`, { ref_externo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: gatewayRefsKeys.list(planoId) }),
  });
}

export function useDeleteGatewayRef(planoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (gateway: Gateway) => api.delete(`/api/planos/${planoId}/gateway-refs/${gateway}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: gatewayRefsKeys.list(planoId) }),
  });
}

/**
 * Julia › Agente = LINE ROUTING only (julia-v2 CONTRACT Q4, white-label per org).
 *
 *   GET /api/julia/roteamento                          org member: the org's WhatsApp lines + handoff default
 *   PUT /api/julia/roteamento/linhas/{connection_id}   admin: {alimenta, destino_handoff_user_id?}
 *
 * How Julia BEHAVES is maintained by the platform; SW only decides which numbers feed her and who is told when
 * a lead goes to a human. Loading = two signals off `data` (never `isLoading`).
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";

export interface LinhaRoteamento {
  connection_id: string;
  label: string;
  /** "this number feeds the agent" (the routing switch; NOT the agent's own on/off, which lives in agents). */
  alimenta: boolean;
  alimenta_desde: string | null;
  /** Informational only: it no longer gates turning the line on. */
  numeros_autorizados?: number;
  /** null = the default (the org owner). */
  destino_handoff_user_id: string | null;
}

export interface Roteamento {
  linhas: LinhaRoteamento[];
  destino_handoff_padrao: { tipo: string; user_id: string | null };
  /** Where the Julia is published/controlled (link shown only when the switch is blocked by agents). */
  agents_url?: string | null;
}

export interface LinhaUpdate {
  alimenta: boolean;
  /** Omit = keep; explicit null = back to the default (the org owner). */
  destino_handoff_user_id?: string | null;
}

export const JULIA_ROTEAMENTO_KEY = ["sw", "julia", "roteamento"] as const;

export function useJuliaRoteamento() {
  return useQuery({
    queryKey: JULIA_ROTEAMENTO_KEY,
    queryFn: async () => (await api.get<{ data: Roteamento }>("/api/julia/roteamento")).data,
  });
}

export function useAtualizarLinha() {
  return useCacheWriteMutation<unknown, { connectionId: string; body: LinhaUpdate }>({
    mutationFn: ({ connectionId, body }) => api.put(`/api/julia/roteamento/linhas/${connectionId}`, body),
    // The switch and the handoff target are exactly what the user sent; `alimenta_desde` is the server's (settle).
    targets: ({ connectionId, body }) => [
      {
        queryKey: JULIA_ROTEAMENTO_KEY,
        optimistic: (old: Roteamento | undefined) =>
          listOps.within(old, "linhas", (l) =>
            listOps.patch(
              l,
              connectionId,
              {
                alimenta: body.alimenta,
                ...(body.destino_handoff_user_id !== undefined ? { destino_handoff_user_id: body.destino_handoff_user_id } : {}),
              },
              "connection_id",
            ),
          ),
      },
    ],
  });
}

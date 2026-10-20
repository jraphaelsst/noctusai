/**
 * Julia › Agente = LINE ROUTING only (julia-v2 CONTRACT Q4, white-label per org).
 *
 *   GET /api/julia/roteamento                          org member: the org's WhatsApp lines + handoff default + agents link
 *   PUT /api/julia/roteamento/linhas/{connection_id}   admin: {alimenta, destino_handoff_user_id?}
 *
 * How Julia BEHAVES is configured in the agents app; SW only decides which numbers feed her and who is told when
 * a lead goes to a human. Loading = two signals off `data` (never `isLoading`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface LinhaRoteamento {
  connection_id: string;
  label: string;
  /** "this number feeds the agent" (the routing switch; NOT the agent's own on/off, which lives in agents). */
  alimenta: boolean;
  alimenta_desde: string | null;
  numeros_autorizados: number;
  /** null = the default (the org owner). */
  destino_handoff_user_id: string | null;
}

export interface Roteamento {
  linhas: LinhaRoteamento[];
  destino_handoff_padrao: { tipo: string; user_id: string | null };
  /** Base URL of the agents app, resolved server-side. Null = unresolvable. */
  agents_url: string | null;
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
  const qc = useQueryClient();
  return useMutation<unknown, unknown, { connectionId: string; body: LinhaUpdate }>({
    mutationFn: ({ connectionId, body }) => api.put(`/api/julia/roteamento/linhas/${connectionId}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: JULIA_ROTEAMENTO_KEY }),
  });
}

/** Where Julia is configured, in the agents app (Studio). Null when the agents URL is unresolvable. */
export function urlConfigurarJulia(agentsUrl: string | null | undefined): string | null {
  return agentsUrl ? `${agentsUrl.replace(/\/$/, "")}/studio/julia` : null;
}

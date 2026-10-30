/**
 * Unified agent surface hooks — agents-unified CONTRACT §2/§4:
 * `GET /api/agents/painel` (one card per agent), `GET /api/agents/{key}/painel` (the page header),
 * `GET /api/studio/modelo` (the page map), `GET /api/agents/{key}/painel/interno` (superadmin internals).
 *
 * Loading contract (KB § PATTERNS/frontend/lying-loading-state.md): `showSkeleton` only while there is NO data
 * yet; a background refetch keeps the data on screen (`isRefreshing`). Never `isLoading`.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AgenteInterno, AgenteModelo, AgentePainel, AgentesPainelResponse } from "@/api/agentes/types";

export const AGENTES_PAINEL_KEY = ["agents", "painel"] as const;

export function agentePainelKey(key: string) {
  return ["agents", "painel", key] as const;
}

function estados<T>(query: { data: T | undefined; isPending: boolean; isFetching: boolean; isError: boolean }) {
  return {
    showSkeleton: query.isPending && query.data === undefined,
    isRefreshing: query.isFetching && query.data !== undefined,
    isError: query.isError,
  };
}

export function useAgentesPainel() {
  const query = useQuery<AgentesPainelResponse>({
    queryKey: AGENTES_PAINEL_KEY,
    queryFn: () => api.get<AgentesPainelResponse>("/api/agents/painel"),
  });
  return { data: query.data?.items, ...estados(query), error: query.error, refetch: query.refetch };
}

export function useAgentePainel(key: string) {
  const query = useQuery<AgentePainel>({
    queryKey: agentePainelKey(key),
    queryFn: () => api.get<AgentePainel>(`/api/agents/${encodeURIComponent(key)}/painel`),
    enabled: key.length > 0,
  });
  return { data: query.data, ...estados(query), error: query.error, refetch: query.refetch };
}

export function useAgenteModelo() {
  const query = useQuery<AgenteModelo>({
    queryKey: ["agents", "modelo"],
    queryFn: () => api.get<AgenteModelo>("/api/studio/modelo"),
    staleTime: 5 * 60_000,
  });
  return { data: query.data, ...estados(query), error: query.error, refetch: query.refetch };
}

/** Asked only when the page already shows an internal section (the server decided the caller is a superadmin). */
export function useAgenteInterno(key: string, enabled: boolean) {
  const query = useQuery<AgenteInterno>({
    // Outside the painel family on purpose: internals (versions, draft, content status) are not touched by the
    // on/off write that patches the painel caches.
    queryKey: ["agents", "interno", key],
    queryFn: () => api.get<AgenteInterno>(`/api/agents/${encodeURIComponent(key)}/painel/interno`),
    enabled: enabled && key.length > 0,
    retry: false,
  });
  return { data: query.data, ...estados(query), error: query.error };
}

export interface DestinoChat {
  key: string;
  /** `academia` = the agent the academia principal names · `legado` = the org's code-defined chat agent. */
  origem: "academia" | "legado";
}

/**
 * Where the old academia chat URLs (`/bia`, `/julia`, `/agentes/bia/persona`) lead now — decided by the server from
 * data (Renata cutover), never a key hard-coded here. `notFound` = the org has no in-app chat agent.
 */
export function useDestinoChat() {
  const query = useQuery<DestinoChat>({
    queryKey: ["agents", "destino-chat"],
    queryFn: () => api.get<DestinoChat>("/api/agents/painel/destino-chat"),
    retry: false,
  });
  return { data: query.data, ...estados(query), error: query.error };
}

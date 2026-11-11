/** Data layer of the Google connection (`/api/google/*`, admin-only on the server). No route returns a token. */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";

export interface GoogleStatus {
  connected: boolean;
  account_email: string | null;
  scopes: string[];
  missing_scopes: string[];
  connected_at: string | null;
  needs_reconnection: boolean;
  app_scopes: string[];
}

export type ProvaStatus = "ok" | "sem_permissao" | "reconectar" | "erro";
export interface GoogleProva {
  calendario: { status: ProvaStatus; itens: { titulo: string; inicio: string | null }[] };
  drive: { status: ProvaStatus; itens: { nome: string; tipo: string; modificado_em: string | null }[] };
  needs_reconnection: boolean;
}

export const googleKeys = {
  status: ["google", "status"] as const,
  prova: ["google", "prova"] as const,
};

export function useGoogleStatus(enabled = true) {
  return useQuery({ queryKey: googleKeys.status, queryFn: () => api.get<GoogleStatus>("/api/google/status"), enabled });
}

/** On demand only (the owner presses "Testar conexão"): two live Google reads, never polled. */
export function useGoogleProva(enabled: boolean) {
  return useQuery({
    queryKey: googleKeys.prova,
    queryFn: () => api.get<GoogleProva>("/api/google/prova"),
    enabled,
    retry: false,
  });
}

/** Asks the server for the Google consent URL (it mints the single-use state); the caller navigates to it. */
export function useGoogleConnect() {
  return useCacheWriteMutation<{ url: string }, void>({
    mutationFn: () => api.post<{ url: string }>("/api/google/connect/start", {}),
    targets: [{ queryKey: googleKeys.status }],
  });
}

export function useGoogleDisconnect() {
  return useCacheWriteMutation<{ connected: boolean; revoked: boolean | null }, void>({
    mutationFn: () => api.post<{ connected: boolean; revoked: boolean | null }>("/api/google/disconnect", {}),
    targets: [
      {
        queryKey: googleKeys.status,
        commit: (old: GoogleStatus | undefined) =>
          old ? { ...old, connected: false, account_email: null, scopes: [], missing_scopes: [], connected_at: null, needs_reconnection: false } : old,
      },
      // the proof belonged to the connection that just ended
      { queryKey: googleKeys.prova, commit: () => undefined },
    ],
  });
}

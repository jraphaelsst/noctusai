/**
 * Channel-integration hooks — the Módulo 5 credential setup surface.
 *
 * Backend mirror: `app/routers/integracoes_router.py`.
 *
 * There is no `token` in any type here, deliberately: the API never returns
 * one, and modelling it would invite a component to try to render it.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Canal } from "@/hooks/useDistribuicao";

export type OrigemCredencial = "org" | "env" | "nenhuma";

export interface IntegracaoStatus {
  canal: Canal;
  conectado: boolean;
  origem: OrigemCredencial;
  conta_externa: string | null;
  conectado_em: string | null;
  /** Set after an auth failure — the UI turns this into "reconectar". */
  ultimo_erro: string | null;
  /** Whether `IGIG_COFRE_KEY` is set on this deploy. Same value on every
   * channel — shown so the setup screen can say so BEFORE a save fails. */
  cofre_configurado: boolean;
}

export const INTEGRACOES_QUERY_KEY = ["igig", "integracoes"] as const;

export function useIntegracoes() {
  const query = useQuery({
    queryKey: INTEGRACOES_QUERY_KEY,
    queryFn: () => api.get<IntegracaoStatus[]>("/api/integracoes"),
  });
  return {
    ...query,
    integracoes: query.data ?? [],
    loading: query.isPending && !query.data,
    // One key encrypts every channel, so every entry carries the same
    // value — read off the first once the list has loaded. `null` (not
    // `false`) while unknown, so a caller can tell "not configured" apart
    // from "hasn't loaded yet" and never flash a false warning.
    cofreConfigurado: query.data ? query.data[0]?.cofre_configurado ?? false : null,
  };
}

export function useConectarCanal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ canal, token, conta_externa }: {
      canal: Canal; token: string; conta_externa?: string;
    }) => api.post<IntegracaoStatus>(`/api/integracoes/${canal}`, { token, conta_externa }),
    onSuccess: () => qc.invalidateQueries({ queryKey: INTEGRACOES_QUERY_KEY }),
  });
}

export function useDesconectarCanal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (canal: Canal) => api.delete<{ ok: boolean }>(`/api/integracoes/${canal}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: INTEGRACOES_QUERY_KEY }),
  });
}

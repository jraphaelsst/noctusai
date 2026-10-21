/**
 * Channel-integration hooks — the Módulo 5 credential setup surface.
 *
 * Backend mirror: `app/routers/integracoes_router.py`.
 *
 * There is no `token` in any type here, deliberately: the API never returns
 * one, and modelling it would invite a component to try to render it.
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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

/** Rows are keyed by `canal`, not `id` — so the status list is edited by channel. */
function porCanal(
  old: IntegracaoStatus[] | undefined,
  canal: Canal,
  changes: Partial<IntegracaoStatus>,
): IntegracaoStatus[] | undefined {
  if (!Array.isArray(old)) return old;
  return old.map((i) => (i.canal === canal ? { ...i, ...changes } : i));
}

export function useConectarCanal() {
  type Vars = { canal: Canal; token: string; conta_externa?: string };
  return useCacheWriteMutation<IntegracaoStatus, Vars>({
    mutationFn: ({ canal, token, conta_externa }) =>
      api.post<IntegracaoStatus>(`/api/integracoes/${canal}`, { token, conta_externa }),
    // The server's status for the channel (conectado, conta, cofre) replaces its row.
    targets: [{ queryKey: INTEGRACOES_QUERY_KEY, commit: (old, saved) => porCanal(old, saved.canal, saved) }],
  });
}

export function useDesconectarCanal() {
  return useCacheWriteMutation<{ ok: boolean }, Canal>({
    mutationFn: (canal) => api.delete<{ ok: boolean }>(`/api/integracoes/${canal}`),
    targets: [
      {
        queryKey: INTEGRACOES_QUERY_KEY,
        // The org's own credential is gone; an env fallback (if any) shows on settle.
        optimistic: (old, canal) =>
          porCanal(old, canal, { conectado: false, origem: "nenhuma", conta_externa: null, conectado_em: null, ultimo_erro: null }),
      },
    ],
  });
}

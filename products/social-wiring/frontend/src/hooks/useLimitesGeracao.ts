/**
 * Daily generation limits — GET/PUT /api/settings/limites-geracao (geracao-contract.md §9.4.1).
 *
 * Read: any org member. Write: org owner/admin (the backend's `require_org_admin_for`). Every answer is the WHOLE
 * list, so a save writes it straight into the cache (the screen never waits on a refetch to agree with the server).
 *
 * 🔴 `loading` = `isPending && !data` (the skeleton signal), never `isLoading`; `isRefreshing` is indicator-only.
 * → KB § PATTERNS/frontend/lying-loading-state.md
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

export type LimiteEscopo = "usuario" | "marca" | "org";

export interface LimiteGeracao {
  chave: string;
  rotulo: string;
  descricao: string;
  escopo: LimiteEscopo;
  /** The limit in force for this org. */
  valor: number;
  /** What "Restaurar padrão" brings back (platform → env → app default). */
  padrao: number;
  /** The platform ceiling: a limit is never unlimited. */
  maximo: number;
  /** This org has its own value. */
  personalizado: boolean;
}

export interface LimitesGeracaoLista {
  items: LimiteGeracao[];
  total: number;
}

/** `null` restores the default. */
export type LimitesGeracaoSave = Record<string, number | null>;

export const LIMITES_GERACAO_KEY = ["settings", "limites-geracao"] as const;
const URL = "/api/settings/limites-geracao";

/** The settings section the daily-limit 429s link to. */
export const ROTA_LIMITES_DIARIOS = "/configuracoes/limites";

export function useLimitesGeracao() {
  const query = useQuery({
    queryKey: LIMITES_GERACAO_KEY,
    queryFn: () => api.get<LimitesGeracaoLista>(URL),
  });
  return {
    ...query,
    loading: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useSalvarLimitesGeracao() {
  return useCacheWriteMutation<LimitesGeracaoLista, LimitesGeracaoSave>({
    mutationFn: (limites) => api.put<LimitesGeracaoLista>(URL, { limites }),
    // The answer is the whole re-resolved list: it replaces the cached one.
    targets: [{ queryKey: LIMITES_GERACAO_KEY, commit: (_old: LimitesGeracaoLista | undefined, saved) => saved }],
  });
}

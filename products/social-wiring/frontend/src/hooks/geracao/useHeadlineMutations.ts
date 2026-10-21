/**
 * Headline mutations over `/api/media-creation/headlines` (contract §4.4
 * #27 edit · #28 favoritar/desfavoritar · #30 excluir). Every mutation
 * writes the server row into the cached headline reads (lists, lote detail, `um`) and
 * settles by invalidating the whole `["sw","geracao"]` family (headline lists, lotes,
 * dashboard) so P1/P2/P7–P9 stay consistent.
 */
import { api } from "@noctusai/seed/infra";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import type { Headline } from "@/types/geracao";
import { GERACAO_KEY } from "@/lib/geracaoKeys";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

const BASE = "/api/media-creation/headlines";

const HEAD_KEY = [...GERACAO_KEY, "headlines"] as const;

/**
 * Put one headline into every cached read that can hold it: `{items}` pages
 * (favoritas/sugeridas), a lote detail's `headlines[]`, and the `um` detail
 * itself. Rows that are not on a cached read are left alone (settle converges).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function putHeadline(old: any, id: string, changes: Partial<Headline>): any {
  if (old && typeof old === "object" && !Array.isArray(old) && old.id === id && "texto" in old) {
    return { ...old, ...changes };
  }
  return pageOps.patch(listOps.within(old, "headlines", (l) => listOps.patch(l, id, changes) ?? l), id, changes);
}

export function useEditarHeadline() {
  return useCacheWriteMutation<Headline, { id: string; texto: string }>({
    mutationFn: async (v) =>
      unwrap(
        await api.patch<Envelope<Headline>>(`${BASE}/${encodeURIComponent(v.id)}`, {
          texto: v.texto,
        }),
      ),
    targets: (v) => [
      {
        queryKey: HEAD_KEY,
        match: "prefix",
        optimistic: (old, vars) => putHeadline(old, vars.id, { texto: vars.texto }),
        commit: (old, saved) => putHeadline(old, v.id, saved),
      },
    ],
    invalidate: [GERACAO_KEY],
  });
}

export function useFavoritarHeadline() {
  return useCacheWriteMutation<Headline, { id: string; favoritar: boolean }>({
    mutationFn: async (v) =>
      unwrap(
        await api.post<Envelope<Headline>>(
          `${BASE}/${encodeURIComponent(v.id)}/${v.favoritar ? "favoritar" : "desfavoritar"}`,
        ),
      ),
    targets: (v) => [
      {
        queryKey: HEAD_KEY,
        match: "prefix",
        optimistic: (old, vars) => putHeadline(old, vars.id, { favorita: vars.favoritar }),
        commit: (old, saved) => putHeadline(old, v.id, saved),
      },
    ],
    // The favoritas list membership is the server's call.
    invalidate: [GERACAO_KEY],
  });
}

export function useExcluirHeadlines() {
  return useCacheWriteMutation<{ excluidos: number }, string[]>({
    mutationFn: async (ids) =>
      unwrap(await api.post<Envelope<{ excluidos: number }>>(`${BASE}/excluir`, { ids })),
    targets: (ids) => [
      {
        queryKey: HEAD_KEY,
        match: "prefix",
        optimistic: (old) =>
          ids.reduce(
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (acc: any, id) => pageOps.remove(listOps.within(acc, "headlines", (l) => listOps.remove(l, id) ?? l), id),
            old,
          ),
      },
    ],
    invalidate: [GERACAO_KEY],
  });
}

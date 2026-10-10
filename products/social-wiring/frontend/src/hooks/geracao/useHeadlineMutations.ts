/**
 * Headline mutations over `/api/media-creation/headlines` (contract §4.4
 * #27 edit · #28 favoritar/desfavoritar · #30 excluir). Every mutation
 * invalidates the whole `["sw","geracao"]` family (headline lists, lotes,
 * dashboard) so P1/P2/P7–P9 stay consistent.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { Headline } from "@/types/geracao";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

const BASE = "/api/media-creation/headlines";
export const GERACAO_KEY = ["sw", "geracao"] as const;

function useInvalidateGeracao() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: GERACAO_KEY });
}

export function useEditarHeadline() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (v: { id: string; texto: string }) =>
      unwrap(
        await api.patch<Envelope<Headline>>(`${BASE}/${encodeURIComponent(v.id)}`, {
          texto: v.texto,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useFavoritarHeadline() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (v: { id: string; favoritar: boolean }) =>
      unwrap(
        await api.post<Envelope<Headline>>(
          `${BASE}/${encodeURIComponent(v.id)}/${v.favoritar ? "favoritar" : "desfavoritar"}`,
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useExcluirHeadlines() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (ids: string[]) =>
      unwrap(await api.post<Envelope<{ excluidos: number }>>(`${BASE}/excluir`, { ids })),
    onSuccess: invalidate,
  });
}

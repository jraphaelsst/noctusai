/**
 * Opt-outs dos leads -- `GET /api/studio/opt-outs` (membro, paginado por cursor, mais recente primeiro) e
 * `POST /api/studio/opt-outs/{id}/notificar` (admin: reenvia o aviso que falhou).
 *
 * LOADING (`KB § PATTERNS/frontend/lying-loading-state.md`): `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data` -- nunca `isLoading`. "Carregar mais" tem o próprio sinal
 * (`isFetchingMore`), para a lista já exibida nunca desmontar enquanto a próxima página chega.
 */
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { OptOutEvento, OptOutEventosPage } from "@/api/studio/types-julia";

export const optOutKeys = { all: ["agents", "opt-outs"] as const };

const PAGE_SIZE = 50;

export function useOptOuts() {
  const q = useInfiniteQuery<OptOutEventosPage>({
    queryKey: optOutKeys.all,
    queryFn: ({ pageParam }) =>
      api.get<OptOutEventosPage>("/api/studio/opt-outs", {
        limit: PAGE_SIZE,
        ...(pageParam ? { cursor: pageParam as string } : {}),
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
  });
  const items = q.data?.pages.flatMap((p) => p.items);
  return {
    items,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data && !q.isFetchingNextPage,
    isFetchingMore: q.isFetchingNextPage,
    hasMore: !!q.hasNextPage,
    fetchMore: () => {
      void q.fetchNextPage();
    },
    isError: q.isError,
    error: q.error,
    refetch: () => {
      void q.refetch();
    },
  };
}

export function useReenviarNotificacao() {
  const qc = useQueryClient();
  return useMutation<OptOutEvento, unknown, string>({
    mutationFn: (eventoId) => api.post<OptOutEvento>(`/api/studio/opt-outs/${encodeURIComponent(eventoId)}/notificar`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: optOutKeys.all });
      // the thread banner reads the same event through the conversation list
      void qc.invalidateQueries({ queryKey: ["studio"] });
    },
  });
}

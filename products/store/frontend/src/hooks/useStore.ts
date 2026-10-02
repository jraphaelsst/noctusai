/**
 * Store data hooks — one place for every query/mutation (never inline in pages).
 *
 * Loading rule (CLAUDE.md, no lying loading states): consumers read
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`,
 * computed HERE so no page re-derives (or mis-derives) them.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAdminSettings,
  fetchKitFile,
  fetchPedido,
  fetchPedidosAdmin,
  fetchPublicSettings,
  postCheckout,
  putAdminSettings,
  reenviarPedido,
  uploadAutorFoto,
  uploadKitFile,
  type StoreSettings,
} from "@/lib/api";

export const POLL_INTERVAL_MS = 3000;
export const POLL_MAX_MS = 2 * 60 * 1000;

export function usePublicSettings() {
  const q = useQuery({
    queryKey: ["store", "public-settings"],
    queryFn: fetchPublicSettings,
    staleTime: 60_000,
    retry: 1,
  });
  return {
    ...q,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
  };
}

export function useCheckout() {
  return useMutation({ mutationFn: postCheckout });
}

/**
 * Polls the buyer's order every 3 s while it is `pendente`. The 2-minute
 * give-up window is owned by the page (`stopPolling`), so the wall-clock lives
 * next to the message it switches.
 */
export function usePedido(token: string | null, stopPolling = false) {
  const q = useQuery({
    queryKey: ["store", "pedido", token],
    queryFn: () => fetchPedido(token as string),
    enabled: !!token,
    retry: false,
    refetchInterval: (query) => {
      if (stopPolling) return false;
      const status = query.state.data?.status;
      return status && status !== "pendente" ? false : POLL_INTERVAL_MS;
    },
  });
  return { ...q, showSkeleton: q.isPending && !q.data && !!token };
}

export function useAdminSettings() {
  const q = useQuery({
    queryKey: ["store", "admin-settings"],
    queryFn: fetchAdminSettings,
    retry: false,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ data, version }: { data: StoreSettings; version: number }) =>
      putAdminSettings(data, version),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["store", "admin-settings"] });
      void qc.invalidateQueries({ queryKey: ["store", "public-settings"] });
    },
  });
}

export function useUploadFoto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: uploadAutorFoto,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["store", "admin-settings"] });
      void qc.invalidateQueries({ queryKey: ["store", "public-settings"] });
    },
  });
}

export function useKitFile() {
  const q = useQuery({ queryKey: ["store", "kit-file"], queryFn: fetchKitFile, retry: false });
  return { ...q, showSkeleton: q.isPending && !q.data };
}

export function useUploadKit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: uploadKitFile,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["store", "kit-file"] }),
  });
}

export function usePedidosAdmin() {
  const q = useQuery({
    queryKey: ["store", "pedidos-admin"],
    queryFn: fetchPedidosAdmin,
    retry: false,
    placeholderData: (prev) => prev,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

export function useReenviar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: reenviarPedido,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["store", "pedidos-admin"] }),
  });
}

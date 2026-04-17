import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from "sonner";
import type { Watchlist, WatchlistItem } from "@/types";

export function useWatchlists() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["watchlists"],
    queryFn: async () => {
      const result = await api.get("/api/watchlists");
      return (result.data || []) as Watchlist[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useWatchlist(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["watchlist", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/watchlists/${id}`);
      return result.data as Watchlist;
    },
    enabled: !!user && !!id,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { nome: string }) => {
      const result = await api.post("/api/watchlists", data);
      return result.data as Watchlist;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      toast.success("Watchlist criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar watchlist", { description: error.message });
    },
  });
}

export function useDeleteWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/watchlists/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      toast.success("Watchlist excluida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao excluir watchlist", { description: error.message });
    },
  });
}

export function useAddWatchlistItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string; ticker: string; nome?: string; alerta_preco_acima?: number; alerta_preco_abaixo?: number; notas?: string }) => {
      const result = await api.post(`/api/watchlists/${id}/itens`, data);
      return result.data as WatchlistItem;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      toast.success("Ativo adicionado a watchlist!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao adicionar ativo", { description: error.message });
    },
  });
}

export function useRemoveWatchlistItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (itemId: string) => {
      await api.delete(`/api/watchlists/itens/${itemId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      toast.success("Ativo removido da watchlist!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover ativo", { description: error.message });
    },
  });
}

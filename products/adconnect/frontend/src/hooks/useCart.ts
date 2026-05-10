/**
 * useCart — React Query hooks for the distributor cart.
 *
 * Phase 7 PROPER: wired to backend endpoints (Engineer E ships these in
 * Wave 3 — endpoints may not be live at consumption time but the contract
 * is locked in `app/schemas/orders.py`). The mutation hook invalidates
 * cart + order queries on success so list views refresh.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from "@noctusai/seed/infra";
import { toast } from "sonner";
import type { Cart, CartItem } from "@/types";

export function useCart() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["adconnect", "cart"],
    queryFn: async () => {
      const result = await api.get("/api/cart");
      return (result.data || null) as Cart | null;
    },
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useCartMutations() {
  const queryClient = useQueryClient();

  const addItem = useMutation({
    mutationFn: async (data: { product_id: string; quantidade: number }) => {
      const result = await api.post("/api/cart/items", data);
      return result.data as CartItem;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "cart"] });
      toast.success("Item adicionado ao carrinho");
    },
    onError: (error: Error) => {
      toast.error("Erro ao adicionar item", { description: error.message });
    },
  });

  const updateItem = useMutation({
    mutationFn: async ({ id, quantidade }: { id: string; quantidade: number }) => {
      const result = await api.patch(`/api/cart/items/${id}`, { quantidade });
      return result.data as CartItem;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "cart"] });
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar quantidade", { description: error.message });
    },
  });

  const removeItem = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/cart/items/${id}`);
      return id;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "cart"] });
      toast.success("Item removido do carrinho");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover item", { description: error.message });
    },
  });

  const checkout = useMutation({
    mutationFn: async (data: { observacoes?: string }) => {
      const result = await api.post("/api/cart/checkout", data ?? {});
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "cart"] });
      queryClient.invalidateQueries({ queryKey: ["adconnect", "orders"] });
      toast.success("Pedido realizado com sucesso");
    },
    onError: (error: Error) => {
      toast.error("Erro ao finalizar pedido", { description: error.message });
    },
  });

  return { addItem, updateItem, removeItem, checkout };
}
